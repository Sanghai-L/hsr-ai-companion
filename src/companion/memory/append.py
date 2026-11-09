"""Append classifications and scope, never account facts or replacement content."""
import json

from companion.contracts import CompanionError, ErrorCode, ToolResult, canonical
from companion.sources.evidence import EvidenceService
from companion.storage.paths import file_lock

KINDS = {"fact", "preference", "discussion", "hypothesis", "conclusion"}


class MemoryAppend:
    def __init__(self, store):
        self.store = store

    def append(self, account_id, record_type, title, body, summary, *, topic, entities=None, game_version=None,
               conditions=None, evidence_ids=None, experiment_ids=None, source_refs=None, claim_key=None, fact_basis=None):
        self.store.require_account(account_id)
        if record_type not in KINDS or not isinstance(summary, str) or not summary.strip() or len(summary) > 1500:
            raise CompanionError(ErrorCode.INVALID_INPUT, "记忆分类或摘要无效")
        if not topic.strip() or len(topic) > 200 or len(entities or []) > 20 or len(conditions or []) > 20:
            raise CompanionError(ErrorCode.INVALID_INPUT, "主题或条件超限")
        if record_type == "conclusion" and (not claim_key or not conditions or not (evidence_ids or experiment_ids or source_refs)):
            raise CompanionError(ErrorCode.MISSING_DATA, "结论需要稳定论点键、适用条件和证据／实验引用")
        if record_type == "fact" and (fact_basis not in {"user_statement", "observed_source"} or not (source_refs or evidence_ids)):
            raise CompanionError(ErrorCode.INVALID_INPUT, "事实需要明确来源；假设应使用 hypothesis 分类")
        for evidence_id in evidence_ids or []:
            EvidenceService(self.store).get(account_id, evidence_id)
        for experiment_id in experiment_ids or []:
            with self.store.connection() as connection:
                if connection.execute("SELECT 1 FROM experiments WHERE account_id=? AND id=?", (account_id, experiment_id)).fetchone() is None:
                    raise CompanionError(ErrorCode.MISSING_DATA, "此账号没有引用的实验")
        metadata = {"memory_schema": 1, "record_type": record_type, "summary": summary, "topic": topic,
                    "entities": entities or [], "game_version": game_version, "conditions": conditions or [],
                    "evidence_ids": evidence_ids or [], "experiment_ids": experiment_ids or [], "source_refs": source_refs or [],
                    "claim_key": claim_key, "fact_basis": fact_basis, "disposition": "active"}
        if len(canonical(metadata)) > 24000:
            raise CompanionError(ErrorCode.INVALID_INPUT, "记忆元信息超限")
        with file_lock(self.store.files, "memory.lock"):
            self.store.recover_research()
            if record_type == "conclusion":
                with self.store.connection() as connection:
                    rows = connection.execute("SELECT r.id,r.metadata FROM memory_heads h JOIN research r ON r.id=h.current_id AND r.account_id=h.account_id WHERE h.account_id=?", (account_id,)).fetchall()
                for row in rows:
                    prior = json.loads(row["metadata"])
                    if (prior.get("record_type") == "conclusion" and prior.get("claim_key") == claim_key and
                            prior.get("game_version") == game_version and set(prior.get("entities", [])) == set(entities or [])):
                        old_body = self.store.read_research(account_id, row["id"])
                        if old_body == body and prior.get("conditions") == (conditions or []):
                            return ToolResult(data={"research_id": row["id"], "appended": False, "state": "duplicate"})
                        raise CompanionError(ErrorCode.CONFLICT, "同一论点已有结论；请创建冲突方案后确认修订", details={"research_id": row["id"], "operation": "memory_conflict_propose"})
            research_id = self.store.create_research(account_id, title, body, metadata=metadata)
        return ToolResult(data={"research_id": research_id, "account_id": account_id, "record_type": record_type,
                                "appended": True, "account_facts_modified": False},
                          warnings=["个人研究按本条条件与版本保存；假设不写入账号事实"])
