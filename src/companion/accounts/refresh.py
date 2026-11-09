"""Explicit import/refresh actions only; provider TTL never creates permission."""
import hashlib
import json
import time
import uuid

from companion.contracts import CompanionError, ErrorCode, ToolResult, canonical, validate
from companion.storage.database import now
from .merge import merge
from .providers.enka import EnkaProvider, normalize


class AccountRefresh:
    def __init__(self, store, *, provider=None, clock=time.time, offline=False):
        self.store, self.provider, self.clock, self.offline = store, provider or EnkaProvider(), clock, offline

    def refresh(self, account_id, request_ref, purpose):
        if purpose not in {"import", "refresh"} or not isinstance(request_ref, str) or not request_ref.strip() or len(request_ref) > 2000:
            raise CompanionError(ErrorCode.CONFIRMATION_REQUIRED, "需关联玩家本次明确导入或刷新的请求")
        account = self.store.require_account(account_id)
        if not account["uid"] or not account["region"]:
            raise CompanionError(ErrorCode.MISSING_DATA, "导入前需要 UID 和区服")
        if self.offline:
            raise CompanionError(ErrorCode.NETWORK_FAILURE, "离线模式不查询公开账号")
        # Serialize refreshes per account; this lock is released on crash and never affects other accounts.
        from companion.storage.paths import file_lock
        with file_lock(self.store.files, "uid-" + account_id + ".lock"):
            return self._refresh_locked(account, request_ref, purpose)

    def _refresh_locked(self, account, request_ref, purpose):
        account_id = account["id"]
        with self.store.connection() as connection:
            rows = connection.execute("SELECT * FROM uid_queries WHERE account_id=? AND state='success' ORDER BY created_at DESC,rowid DESC", (account_id,)).fetchall()
        for row in rows:
            cached = json.loads(row["payload"])
            if row["request_ref"] == request_ref or cached["expires_epoch"] > self.clock():
                self.store.append_operation("uid_cache_read", {"request_ref": request_ref, "purpose": purpose, "query_id": row["id"]}, account_id)
                return ToolResult(data={"account_id": account_id, "query_id": row["id"], "snapshot_id": cached["snapshot_id"],
                                        "uid_refreshed": False, "state": "server_cached", "ttl_remaining": max(0, int(cached["expires_epoch"]-self.clock()))},
                                  warnings=["仍在服务端缓存 TTL 内或本次请求已执行；未重新查询，未自动刷新"])
        old = self.store.latest_snapshot(account_id)
        old_id = old["snapshot_id"] if old else None
        query_id = uuid.uuid4().hex
        with self.store.transaction() as connection:
            connection.execute("INSERT INTO uid_queries VALUES(?,?,?,?,?,?,?)", (query_id, account_id, request_ref, purpose, "requested", "{}", now()))
        try:
            payload, raw = self.provider.query(account["uid"])
            remote, ttl, missing = normalize(payload, account_id=account_id, query_id=query_id, observed_at=now(), region=account["region"])
            validate("account-snapshot.schema.json", remote)
            effective, differences = merge(old, remote)
            relative = f"uid/{account_id}/{query_id}.json"
            raw_sha = hashlib.sha256(raw).hexdigest()
            self.store.files.write(relative, canonical({"raw_utf8": raw.decode("utf-8"), "raw_sha256": raw_sha, "remote": remote}), exclusive=True)
            outcome = {"snapshot_id": effective["snapshot_id"], "expires_epoch": self.clock()+ttl, "ttl": ttl,
                       "raw_path": relative, "raw_sha256": raw_sha, "missing_fields": missing, "diff": differences}
            def commit_query(connection):
                connection.execute("UPDATE uid_queries SET state='success',payload=? WHERE id=?", (canonical(outcome).decode(), query_id))
            self.store.put_snapshot(effective, expected_snapshot_id=old_id, transaction_hook=commit_query)
            return ToolResult(data={"account_id": account_id, "query_id": query_id, "snapshot_id": effective["snapshot_id"],
                                    "uid_refreshed": True, "showcase_count": len(remote["characters"]), "roster_completeness": "partial", "ttl": ttl,
                                    "diff_counts": {k: len(v) for k, v in differences.items()}, "manual_conflicts": differences["manual_conflicts"][:10]},
                              missing_fields=missing[:30], warnings=["仅导入公开展示；未展示不代表未持有，背包、星琼和保底仍未知",
                                                                    "装备 instance_id 标记本次展示观察，不证明跨快照真实背包实例身份；缺失旧观察按原日期保留"])
        except CompanionError as error:
            with self.store.transaction() as connection:
                connection.execute("UPDATE uid_queries SET state='failed',payload=? WHERE id=?", (canonical(error.to_dict()).decode(), query_id))
            raise
