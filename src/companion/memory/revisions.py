"""Revision plans bind a trusted player reply, expected old record and exact body."""
import hashlib
import json
import uuid

from companion.contracts import CompanionError, ErrorCode, ToolResult, canonical
from companion.storage.database import now
from companion.storage.paths import file_lock


class Revisions:
    def __init__(self, store):
        self.store = store

    def _row(self, connection, account_id, plan_id):
        row = connection.execute("SELECT * FROM revision_plans WHERE account_id=? AND id=?", (account_id, plan_id)).fetchone()
        if row is None:
            raise CompanionError(ErrorCode.MISSING_DATA, "此账号没有该修订方案")
        plan = json.loads(row["payload"])
        if hashlib.sha256(canonical(plan)).hexdigest() != row["binding_sha256"]:
            raise CompanionError(ErrorCode.CONFLICT, "修订方案指纹变化；旧确认无效")
        return row, plan

    def review(self, account_id, plan_id, *, offset=0, limit=6000):
        with self.store.connection() as connection:
            row, plan = self._row(connection, account_id, plan_id)
        data = {k: v for k, v in plan.items() if k != "new_body"} | {"state": row["state"], "binding_sha256": row["binding_sha256"]}
        actual_limit = min(limit, max(1, (48000-len(canonical(data)))//4))
        data.update(new_body=plan["new_body"][offset:offset+actual_limit], next_offset=offset+actual_limit if offset+actual_limit < len(plan["new_body"]) else None)
        return ToolResult(data=data)

    def record_verified(self, account_id, plan_id, receipt, *, verifier=None):
        """Out-of-band host transcript or TTY adapter; deliberately absent from MCP."""
        with self.store.transaction() as connection:
            row, plan = self._row(connection, account_id, plan_id)
            if row["state"] not in {"proposed", "confirmed"}:
                raise CompanionError(ErrorCode.CONFLICT, "修订方案已执行或失效")
            valid = (isinstance(receipt, dict) and receipt.get("source_kind") in {"user_terminal", "host_native"}
                     and receipt.get("decision") == "approve" and receipt.get("source_ref") and receipt.get("reply_text")
                     and receipt.get("binding_sha256") == row["binding_sha256"])
            if not valid or verifier is None or verifier(receipt, row["binding_sha256"]) is not True:
                raise CompanionError(ErrorCode.CONFIRMATION_REQUIRED, "需要可核验的玩家回复；模型参数不构成确认")
            if row["confirmation"]:
                prior = json.loads(row["confirmation"])
                if prior["source_ref"] == receipt["source_ref"]:
                    return prior["id"]
                raise CompanionError(ErrorCode.CONFLICT, "方案已有不同的确认记录")
            confirmation = {**receipt, "id": uuid.uuid4().hex, "created_at": now()}
            connection.execute("UPDATE revision_plans SET state='confirmed',confirmation=? WHERE id=?", (canonical(confirmation).decode(), plan_id))
            return confirmation["id"]

    def confirm_terminal(self, account_id, plan_id, *, stdin, stdout):
        if not stdin.isatty() or not stdout.isatty():
            raise CompanionError(ErrorCode.CONFIRMATION_REQUIRED, "确认需用户本地交互终端或可信宿主回复适配")
        with self.store.connection() as connection:
            row, plan = self._row(connection, account_id, plan_id)
        phrase = "确认 " + plan_id
        stdout.write(f"账号：{account_id}\n原结论：{plan['expected_id']}\n操作：{plan['action']}\n新摘要：{plan['new_summary']}\n条件：{plan['conditions']}\n新正文：\n{plan['new_body']}\n方案指纹：{row['binding_sha256']}\n输入「{phrase}」记录此方案确认：")
        stdout.flush()
        reply = stdin.readline().strip()
        if reply != phrase:
            raise CompanionError(ErrorCode.CONFIRMATION_REQUIRED, "未收到对具体方案的确认")
        receipt = {"source_kind": "user_terminal", "source_ref": "terminal:" + uuid.uuid4().hex,
                   "decision": "approve", "reply_text": reply, "binding_sha256": row["binding_sha256"]}
        return self.record_verified(account_id, plan_id, receipt, verifier=lambda supplied, digest: supplied is receipt and digest == receipt["binding_sha256"])

    def apply(self, account_id, plan_id, expected_id, confirmation_id):
        with file_lock(self.store.files, "memory.lock"):
            with self.store.connection() as connection:
                row, plan = self._row(connection, account_id, plan_id)
                confirmation = json.loads(row["confirmation"]) if row["confirmation"] else None
                if not confirmation or confirmation["id"] != confirmation_id or confirmation["binding_sha256"] != row["binding_sha256"]:
                    raise CompanionError(ErrorCode.CONFIRMATION_REQUIRED, "此方案没有对应的玩家确认记录")
                if row["state"] == "applied":
                    return ToolResult(data={"plan_id": plan_id, "research_id": row["result_id"], "state": "applied", "idempotent": True})
                if row["state"] != "confirmed":
                    raise CompanionError(ErrorCode.CONFIRMATION_REQUIRED, "方案未确认")
                head = connection.execute("SELECT * FROM memory_heads WHERE account_id=? AND root_id=?", (account_id, plan["root_id"])).fetchone()
                old = connection.execute("SELECT * FROM research WHERE account_id=? AND id=?", (account_id, plan["expected_id"])).fetchone()
            if expected_id != plan["expected_id"] or head["current_id"] != expected_id or head["revision"] != plan["expected_revision"] or old["sha256"] != plan["expected_sha256"]:
                raise CompanionError(ErrorCode.CONFLICT, "旧结论已变化，需重新提出和核对方案")
            self.store.read_research(account_id, expected_id)
            metadata = json.loads(old["metadata"])
            metadata.update(summary=plan["new_summary"], conditions=plan["conditions"], evidence_ids=plan["evidence_ids"],
                            revision_of=plan["root_id"], revision_plan_id=plan_id,
                            disposition="retracted" if plan["action"] == "retract" else "active")
            if len(canonical(metadata)) > 24000:
                raise CompanionError(ErrorCode.BUDGET_EXHAUSTED, "修订元信息超过记忆预算；请缩短摘要或条件后重新提出方案")
            new_id = self.store.create_research(account_id, old["title"], plan["new_body"], metadata=metadata)
            # A crash before this commit leaves a recoverable historical file, never an active unconfirmed revision.
            with self.store.transaction() as connection:
                updated = connection.execute("UPDATE memory_heads SET current_id=?,revision=revision+1 WHERE account_id=? AND root_id=? AND current_id=? AND revision=?",
                                             (new_id, account_id, plan["root_id"], expected_id, plan["expected_revision"]))
                if updated.rowcount != 1:
                    raise CompanionError(ErrorCode.CONFLICT, "并发修订改变了旧版本")
                connection.execute("UPDATE revision_plans SET state='applied',result_id=? WHERE id=?", (new_id, plan_id))
                connection.execute("UPDATE conflicts SET state='resolved' WHERE id=?", (row["conflict_id"],))
                connection.execute("INSERT INTO operations VALUES(?,?,?,?,?)", (uuid.uuid4().hex, account_id, "memory_revision_applied",
                    canonical({"plan_id": plan_id, "old_id": expected_id, "new_id": new_id, "confirmation_id": confirmation_id}).decode(), now()))
            return ToolResult(data={"plan_id": plan_id, "research_id": new_id, "previous_id": expected_id, "state": "applied", "idempotent": False,
                                    "history_preserved": True})
