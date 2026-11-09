"""Bounded relevant summaries, never full unscoped research concatenation."""
from companion.contracts import CompanionError, ErrorCode, ToolResult
from companion.memory.search import MemorySearch


def select_context(store, account_id, *, query="", game_version=None, char_budget=6000, entities=None):
    if not 500 <= char_budget <= 12000:
        raise CompanionError(ErrorCode.INVALID_INPUT, "上下文预算须为 500～12000 字符")
    result = MemorySearch(store).search(account_id, query=query, game_version=game_version, entities=entities, limit=20)
    items, used = [], 0
    for item in result.data["items"]:
        from companion.contracts import canonical
        record = {k: item[k] for k in ("research_id", "record_type", "summary", "game_version", "conditions", "body_ref", "pending_conflicts")}
        # Measure the exact serialized context payload, including source/conflict metadata.
        candidate = {"items": items + [record]}
        if len(canonical(candidate).decode()) > char_budget:
            continue
        items.append(record)
    from companion.contracts import canonical
    used = len(canonical({"items": items}).decode())
    return ToolResult(data={"account_id": account_id, "items": items, "char_budget": char_budget, "chars_used": used,
                            "truncated": len(items) < result.data["total"], "requested_version": game_version}, warnings=result.warnings)
