"""Conflicts attach evidence to an immutable old conclusion, without changing it."""
import hashlib
import json
import uuid

from companion.contracts import CompanionError, ErrorCode, ToolResult, canonical
from companion.sources.evidence import EvidenceService
from companion.storage.database import now
from companion.storage.paths import file_lock


class Conflicts:
    def __init__(self, store):
        self.store = store

    def propose(self, account_id, research_id, evidence_ids, reason, new_body, new_summary, *, action="replace", conditions=None):
        self.store.require_account(account_id)
        if action not in {"replace", "restrict", "retract"} or not evidence_ids or not reason.strip() or len(reason) > 1500:
            raise CompanionError(ErrorCode.INVALID_INPUT, "修订类型、证据或冲突原因无效")
        if not new_body.strip() or len(new_body.encode()) > 96000 or not new_summary.strip() or len(new_summary) > 1500:
            raise CompanionError(ErrorCode.INVALID_INPUT, "修订正文／摘要为空或超限")
        if action == "restrict" and not conditions:
            raise CompanionError(ErrorCode.INVALID_INPUT, "限制适用范围需要具体条件")
        if len(canonical(conditions or [])) > 16000:
            raise CompanionError(ErrorCode.INVALID_INPUT, "修订条件超出单个方案的审阅预算")
        for evidence_id in evidence_ids:
            EvidenceService(self.store).get(account_id, evidence_id)
        with file_lock(self.store.files, "memory.lock"):
            with self.store.transaction() as connection:
                head = connection.execute("SELECT h.*,r.metadata,r.sha256,r.title FROM memory_heads h JOIN research r ON r.id=h.current_id AND r.account_id=h.account_id WHERE h.account_id=? AND (h.current_id=? OR h.root_id=?)", (account_id, research_id, research_id)).fetchone()
                if head is None:
                    raise CompanionError(ErrorCode.MISSING_DATA, "此账号没有可修订的研究")
                prior = json.loads(head["metadata"])
                if prior.get("record_type") != "conclusion":
                    raise CompanionError(ErrorCode.UNSUPPORTED, "本入口只修订研究结论")
                plan_id, conflict_id = uuid.uuid4().hex, uuid.uuid4().hex
                plan = {"plan_id": plan_id, "account_id": account_id, "root_id": head["root_id"], "expected_id": head["current_id"],
                        "expected_sha256": head["sha256"], "expected_revision": head["revision"], "action": action,
                        "evidence_ids": evidence_ids, "reason": reason, "new_body": new_body, "new_summary": new_summary,
                        "conditions": conditions if conditions is not None else prior["conditions"], "created_at": now()}
                digest = hashlib.sha256(canonical(plan)).hexdigest()
                conflict = {"plan_id": plan_id, "expected_id": head["current_id"], "evidence_ids": evidence_ids, "reason": reason}
                connection.execute("INSERT INTO conflicts VALUES(?,?,?,?,?)", (conflict_id, account_id, head["root_id"], "pending", canonical(conflict).decode()))
                connection.execute("INSERT INTO revision_plans VALUES(?,?,?,?,?,?,?,?,?,?)", (
                    plan_id, account_id, conflict_id, head["root_id"], head["current_id"], canonical(plan).decode(), digest, "proposed", None, None))
        return ToolResult(data={"plan_id": plan_id, "conflict_id": conflict_id, "account_id": account_id,
                                "expected_id": plan["expected_id"], "binding_sha256": digest, "action": action,
                                "old_summary": prior["summary"], "new_summary": new_summary, "conditions": plan["conditions"],
                                "state": "awaiting_player_reply", "old_body_unchanged": True},
                          warnings=["方案仅登记冲突；等待玩家对具体方案的回复，不自动覆盖旧研究"])
