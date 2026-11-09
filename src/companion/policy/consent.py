"""Approval receipts enter only through an out-of-band trusted verifier."""
import hashlib
import json
import uuid

from companion.contracts import CompanionError, ErrorCode, canonical
from companion.storage.database import now


def binding(plan):
    return hashlib.sha256(canonical({k: v for k, v in plan.items() if k != "state"})).hexdigest()


class ConsentPolicy:
    def __init__(self, store):
        self.store = store

    def record_verified(self, plan_id, receipt, *, verifier=None):
        """Not registered as an MCP tool; receipt booleans carry no authority."""
        with self.store.transaction() as connection:
            row = connection.execute("SELECT * FROM update_plans WHERE id=?", (plan_id,)).fetchone()
            if row is None or row["state"] != "proposed":
                raise CompanionError(ErrorCode.CONFLICT, "更新方案不存在或已失效")
            plan = json.loads(row["payload"])
            expected = binding(plan)
            valid = (isinstance(receipt, dict) and receipt.get("source_kind") in {"user_terminal", "host_native"}
                     and receipt.get("source_ref") and receipt.get("host_permission") == "approved"
                     and receipt.get("decision") == "approve" and receipt.get("binding_sha256") == expected)
            if not valid or verifier is None or verifier(receipt, expected) is not True:
                raise CompanionError(ErrorCode.CONFIRMATION_REQUIRED, "缺少可核验的用户回复与宿主许可")
            confirmation_id = uuid.uuid4().hex
            connection.execute("INSERT INTO confirmations VALUES(?,?,?,?,?,?,?,?,?)", (
                confirmation_id, plan_id, expected, receipt["source_kind"], receipt["source_ref"],
                "approved", "approve", now(), None))
            connection.execute("UPDATE update_plans SET state='confirmed' WHERE id=?", (plan_id,))
            return confirmation_id

    def consume(self, plan_id, *, package_sha256, scope_path):
        """One-shot authorization for the future installer, not an installer."""
        with self.store.transaction() as connection:
            row = connection.execute("SELECT * FROM update_plans WHERE id=?", (plan_id,)).fetchone()
            consent = connection.execute("SELECT * FROM confirmations WHERE plan_id=?", (plan_id,)).fetchone()
            if row is None or row["state"] != "confirmed" or consent is None or consent["consumed_at"]:
                raise CompanionError(ErrorCode.CONFIRMATION_REQUIRED, "该方案没有可用的一次性确认")
            plan = json.loads(row["payload"])
            if (binding(plan) != row["binding_sha256"] or consent["binding_sha256"] != binding(plan) or
                    plan["package_sha256"] != package_sha256 or plan["scope_path"] != scope_path):
                raise CompanionError(ErrorCode.CONFLICT, "包或作用路径改变；旧确认不可复用")
            connection.execute("UPDATE confirmations SET consumed_at=? WHERE plan_id=?", (now(), plan_id))
            connection.execute("UPDATE update_plans SET state='consumed' WHERE id=?", (plan_id,))
            return {"plan_id": plan_id, "target_version": plan["target_version"], "scope_path": scope_path,
                    "package_sha256": package_sha256, "confirmation_id": consent["id"]}

    def confirm_terminal(self, plan_id, *, stdin, stdout):
        if not stdin.isatty() or not stdout.isatty():
            raise CompanionError(ErrorCode.CONFIRMATION_REQUIRED, "批准需本地终端中的明确用户交互")
        with self.store.connection() as connection:
            row = connection.execute("SELECT payload FROM update_plans WHERE id=?", (plan_id,)).fetchone()
        if row is None:
            raise CompanionError(ErrorCode.MISSING_DATA, "更新方案不存在")
        plan = json.loads(row["payload"])
        phrase = f"批准 {plan_id} {plan['target_version']}"
        stdout.write(f"版本：{plan['target_version']}\n包指纹：{plan['package_sha256']}\n作用路径：{plan['scope_path']}\n输入「{phrase}」记录批准：")
        stdout.flush()
        if stdin.readline().strip() != phrase:
            raise CompanionError(ErrorCode.CONFIRMATION_REQUIRED, "未获得明确批准")
        receipt = {"source_kind": "user_terminal", "source_ref": "terminal:" + uuid.uuid4().hex,
                   "host_permission": "approved", "decision": "approve", "binding_sha256": binding(plan)}
        return self.record_verified(plan_id, receipt, verifier=lambda supplied, digest: supplied is receipt and digest == receipt["binding_sha256"])

