"""Inspect releases; apply only authenticated packages under a bound confirmation."""
import json
import time
import uuid

from companion import PROGRAM_API_VERSION
from companion.contracts import CompanionError, ErrorCode, ToolResult, canonical, validate
from companion.domain.models import version_tuple
from companion.policy.consent import binding
from companion.storage.database import now


class ProgramUpdates:
    def __init__(self, store, scope_path, *, source=None, current_version=PROGRAM_API_VERSION, clock=time.time, interval=21600):
        self.store, self.scope_path, self.source = store, str(scope_path), source
        self.current_version, self.clock, self.interval = current_version, clock, interval

    def propose(self, manifest):
        plan = {"id": uuid.uuid4().hex, "kind": "program", "target_version": manifest["version"],
                "package_sha256": manifest["sha256"], "scope": "program-and-executable-rules",
                "scope_path": self.scope_path, "migrations": [], "state": "proposed", "created_at": now()}
        validate("action-request.schema.json", plan)
        with self.store.transaction() as connection:
            for row in connection.execute("SELECT * FROM update_plans WHERE state IN ('proposed','confirmed')"):
                existing = json.loads(row["payload"])
                if (existing["target_version"] == plan["target_version"] and existing["package_sha256"] == plan["package_sha256"]
                        and existing["scope_path"] == self.scope_path):
                    existing["state"] = row["state"]
                    return existing
                if existing["scope_path"] == self.scope_path:
                    connection.execute("UPDATE update_plans SET state='invalidated' WHERE id=?", (row["id"],))
            connection.execute("INSERT INTO update_plans VALUES(?,?,?,?,?)", (
                plan["id"], canonical(plan).decode(), binding(plan), "proposed", plan["created_at"]))
        return plan

    def check(self, *, force=False, offline=False, target_version=None):
        if self.source is None:
            return ToolResult(status="partial", data={"state": "unconfigured", "latest": False, "available": None},
                              warnings=["尚未配置维护者程序发布源；未确认最新版本"])
        try:
            with self.store.connection() as connection:
                row = connection.execute("SELECT value FROM settings WHERE key='program_checked_at'").fetchone()
            if not force and row and self.clock() - float(row["value"]) < self.interval:
                return ToolResult(data={"state": "cached", "latest": False, "available": None}, warnings=["本次未重新检查程序发布源"])
            manifest = self.source.manifest("program", offline=offline)
            if target_version is not None and manifest["version"] != target_version:
                raise CompanionError(ErrorCode.CONFLICT, "请求版本与维护者当前发布方案不一致")
            available = version_tuple(manifest["version"]) > version_tuple(self.current_version)
            plan = self.propose(manifest) if available else None
            with self.store.transaction() as connection:
                connection.execute("INSERT OR REPLACE INTO settings VALUES('program_checked_at',?)", (str(self.clock()),))
            return ToolResult(data={"state": "update_available" if available else "unchanged", "latest": not available,
                                    "available": available, "plan": plan, "installed": False},
                              warnings=["本次仅生成待批准方案，尚未安装程序"] if available else [])
        except CompanionError as error:
            return ToolResult.failure(error, data={"state": "failed", "latest": False, "installed": False})

    def apply(self, plan_id, confirmation_id, *, offline=False):
        from companion.install import Installer
        from companion.policy import ConsentPolicy
        with self.store.connection() as connection:
            row = connection.execute("SELECT * FROM update_plans WHERE id=?", (plan_id,)).fetchone()
            consent = connection.execute("SELECT * FROM confirmations WHERE id=? AND plan_id=?", (confirmation_id, plan_id)).fetchone()
        if row is None or row["state"] != "confirmed" or consent is None or consent["consumed_at"]:
            raise CompanionError(ErrorCode.CONFIRMATION_REQUIRED, "缺少该更新方案的一次性确认")
        plan = json.loads(row["payload"])
        if plan["scope_path"] != self.scope_path or self.source is None:
            raise CompanionError(ErrorCode.CONFLICT, "更新安装范围或发布源发生变化")
        manifest = self.source.manifest("program", offline=offline)
        if (not manifest.get("signature_verified") or manifest["sha256"] != plan["package_sha256"] or
                manifest["version"] != plan["target_version"]):
            raise CompanionError(ErrorCode.CONFLICT, "发布版本、指纹或签名改变，旧批准无效")
        content = self.source.package(manifest, offline=offline)
        data_dir = self.store.files.root.parent
        installer = Installer(self.scope_path, data_dir, trusted_keys=self.source.trusted_keys, allow_test=self.source.allow_test)
        authorization = {"package_sha256": manifest["sha256"], "scope_path": self.scope_path,
                         "consume": lambda: ConsentPolicy(self.store).consume(plan_id, package_sha256=manifest["sha256"], scope_path=self.scope_path)}
        return ToolResult(data=installer.install(content, expected_sha256=manifest["sha256"], authorization=authorization))

