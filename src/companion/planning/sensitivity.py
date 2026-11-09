"""One or two explicit axes, varied separately; no Monte Carlo claims."""
from copy import deepcopy
import time

from companion.contracts import CompanionError, ErrorCode, ToolResult
from companion.experiments.contracts import check
from companion.simulation.compare import compare
from companion.simulation.rotation import prepare


def summarize(result):
    return {"recommendation_ids": result.data["recommendation_ids"], "ranking_permitted": result.data["ranking_permitted"],
            "outcomes": [{"candidate_id": row["candidate_id"], "expected_damage": row["expected_damage"], "status": row["status"]}
                         for row in result.data["outcomes"]]}


def assign(request, field, value):
    if field == "scenario.target_count":
        request["scenario"]["target_count"] = value
    elif field.startswith("scenario.phases."):
        parts = field.split(".")
        if (len(parts) != 4 or parts[2] not in {"0", "1"} or int(parts[2]) >= len(request["scenario"]["phases"]) or
                parts[3] not in {"damage_taken_multiplier", "hp_above_half", "enemy_slowed"}):
            raise CompanionError(ErrorCode.INVALID_INPUT, "不支持该敏感性字段")
        request["scenario"]["phases"][int(parts[2])][parts[3]] = value
    else:
        raise CompanionError(ErrorCode.INVALID_INPUT, "敏感性仅支持目标数及阶段受伤乘数／血线／减速条件")


def analyze(request, axes, max_seconds, *, clock=time.monotonic):
    check("sensitivity.schema.json", {"request": request, "axes": axes, "max_seconds": max_seconds})
    value = prepare(request)
    if len({a["field"] for a in axes}) != len(axes):
        raise CompanionError(ErrorCode.INVALID_INPUT, "敏感性字段重复")
    deadline = clock() + max_seconds
    # Validate all variants before computing any; unsupported paths never silently disappear.
    variants = []
    for axis in axes:
        for item in axis["values"]:
            variant = deepcopy(value)
            assign(variant, axis["field"], item)
            prepare(variant)
            variants.append((axis["field"], item, variant))
    base = compare(value, cancelled=lambda: clock() >= deadline)
    baseline = summarize(base)
    reports, reversals = [], []
    for field, item, variant in variants:
        if clock() >= deadline:
            break
        result = summarize(compare(variant, cancelled=lambda: clock() >= deadline))
        reversal = (baseline["ranking_permitted"] and result["ranking_permitted"] and
                    set(baseline["recommendation_ids"]) != set(result["recommendation_ids"]))
        report = {"field": field, "value": item, "result": result, "recommendation_changed": reversal}
        reports.append(report)
        if reversal:
            reversals.append({"field": field, "value": item, "before": baseline["recommendation_ids"], "after": result["recommendation_ids"]})
    complete = len(reports) == len(variants) and baseline["ranking_permitted"] and all(r["result"]["ranking_permitted"] for r in reports)
    return ToolResult(status="success" if complete else "partial",
                      data={"scope": "one_axis_at_a_time", "baseline": baseline, "scenarios": reports,
                            "reversal_conditions": reversals, "robust_within_tested_values": complete and not reversals,
                            "complete": complete, "confidence_interval": None,
                            "interpretation": "反转仅在列出的条件值成立；没有扫描连续阈值、联合参数网格或随机置信区间"},
                      sources=base.sources, versions=base.versions, assumptions=base.assumptions,
                      warnings=base.warnings + ["一到两个参数逐项情景复算，不代表全局稳健或实战通关概率"])
