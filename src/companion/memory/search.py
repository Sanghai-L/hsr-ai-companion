"""Account and version-filtered summaries; immutable full text read on demand."""
import json

from companion.contracts import CompanionError, ErrorCode, ToolResult, canonical
from companion.knowledge.index import tokens


class MemorySearch:
    def __init__(self, store):
        self.store = store

    def conflict_list(self, account_id, research_id, *, offset=0, limit=10):
        self.store.require_account(account_id)
        with self.store.connection() as connection:
            row = connection.execute("SELECT metadata FROM research WHERE account_id=? AND id=?", (account_id, research_id)).fetchone()
            if row is None:
                raise CompanionError(ErrorCode.MISSING_DATA, "该账号没有此研究")
            root_id = json.loads(row["metadata"]).get("revision_of", research_id)
            rows = connection.execute("SELECT id,payload FROM conflicts WHERE account_id=? AND research_id=? AND state='pending' ORDER BY rowid DESC", (account_id, root_id)).fetchall()
        items = [{"conflict_id": row["id"], **json.loads(row["payload"])} for row in rows[offset:offset+limit]]
        while len(canonical(items)) > 40000 and len(items) > 1:
            items.pop()
        return ToolResult(data={"items": items, "total": len(rows), "next_offset": offset+len(items) if offset+len(items) < len(rows) else None})

    def conflicts(self, account_id, root_id):
        result = self.conflict_list(account_id, root_id, limit=3).data
        items = []
        for item in result["items"]:
            items.append({**item, "reason": item["reason"][:300], "evidence_ids": item["evidence_ids"][:5]})
        if result["next_offset"] is not None:
            items.append({"additional_pending": result["total"]-len(items), "read_more": "memory_conflicts", "research_id": root_id})
        return items

    def search(self, account_id, *, query="", topic=None, entities=None, game_version=None, record_type=None, limit=10, offset=0):
        self.store.require_account(account_id)
        if not 1 <= limit <= 20 or offset < 0:
            raise CompanionError(ErrorCode.INVALID_INPUT, "记忆检索范围超限")
        with self.store.connection() as connection:
            rows = connection.execute("SELECT r.*,h.root_id,h.revision FROM memory_heads h JOIN research r ON r.id=h.current_id AND r.account_id=h.account_id WHERE h.account_id=? ORDER BY r.created_at DESC,r.rowid DESC", (account_id,)).fetchall()
        selected = []
        terms = set(tokens(query))
        for row in rows:
            metadata = json.loads(row["metadata"])
            if metadata.get("disposition") == "retracted":
                continue
            if game_version is not None and metadata.get("game_version") != game_version:
                continue
            if record_type and metadata.get("record_type") != record_type:
                continue
            if topic and topic.casefold() not in metadata.get("topic", "").casefold():
                continue
            if entities and not set(entities) & set(metadata.get("entities", [])):
                continue
            score = len(terms & set(tokens(row["title"] + " " + metadata.get("summary", "") + " " + metadata.get("topic", "") + " ".join(metadata.get("entities", [])))))
            if query and not score:
                continue
            # Hash validation prevents damaged content being injected through an intact summary index.
            self.store.read_research(account_id, row["id"])
            selected.append({"research_id": row["id"], "root_id": row["root_id"], "revision": row["revision"], "title": row["title"],
                             "summary": metadata["summary"], "record_type": metadata["record_type"], "topic": metadata["topic"],
                             "entities": metadata["entities"], "game_version": metadata["game_version"], "conditions": metadata["conditions"],
                             "evidence_ids": metadata["evidence_ids"], "source_refs": metadata["source_refs"],
                             "body_ref": "memory_read:" + row["id"], "created_at": row["created_at"], "score": score,
                             "pending_conflicts": self.conflicts(account_id, row["root_id"])})
        selected.sort(key=lambda item: -item["score"])  # stable, retains newest ordering on equal relevance
        page = selected[offset:offset+limit]
        while len(canonical(page)) > 46000 and len(page) > 1:
            page.pop()
        return ToolResult(data={"items": page, "total": len(selected),
                                "next_offset": offset+len(page) if offset+len(page) < len(selected) else None},
                          warnings=["各条记录保留自己的版本与条件，不可无条件合并；存在待处理冲突时应同时说明"])

    def read(self, account_id, research_id, *, offset=0, limit=6000):
        self.store.require_account(account_id)
        with self.store.connection() as connection:
            row = connection.execute("SELECT * FROM research WHERE account_id=? AND id=?", (account_id, research_id)).fetchone()
            head = connection.execute("SELECT * FROM memory_heads WHERE account_id=? AND (root_id=? OR current_id=?)", (account_id, research_id, research_id)).fetchone()
        if row is None:
            raise CompanionError(ErrorCode.MISSING_DATA, "该账号没有此研究")
        metadata = json.loads(row["metadata"])
        root_id = metadata.get("revision_of", research_id)
        body = self.store.read_research(account_id, research_id)
        data = {"research_id": research_id, "root_id": root_id, "title": row["title"], "metadata": metadata,
                                "is_current": bool(head and head["current_id"] == research_id),
                                "pending_conflicts": self.conflicts(account_id, root_id)}
        actual_limit = min(limit, max(1, (48000-len(canonical(data)))//4))
        data.update(content=body[offset:offset+actual_limit], next_offset=offset+actual_limit if offset+actual_limit < len(body) else None)
        return ToolResult(data=data)
