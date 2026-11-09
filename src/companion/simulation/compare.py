"""All candidates share one scenario, time window and initial resource policy."""
from datetime import datetime, timezone

from companion import __version__
from companion.contracts import CompanionError, ErrorCode, ToolResult
from companion.jobs import CalculationBudget, StopCalculation
from .rotation import LIMITATION, METHOD, digest, implementation_fingerprint, mechanics, prepare, project
from .explain import explain


def compare(request, *, cancelled=None, clock=None):
    value = prepare(request)
    work = CalculationBudget(value["budget"], cancelled=cancelled, **({"clock": clock} if clock else {}))
    investments = {candidate["investment_key"] for candidate in value["candidates"]}
    unequal = len(investments) != 1
    if unequal and not value.get("difference_declaration"):
        raise CompanionError(ErrorCode.VERSION_INCOMPATIBLE, "候选投资口径不同；请显式说明，不能无声排名")
    outcomes, stop = [], None
    for candidate in value["candidates"]:
        try:
            work.checkpoint("candidates")
            outcomes.append(project(candidate, value["scenario"], work))
        except StopCalculation as stopped:
            stop = stopped.reason
            break
        if outcomes[-1]["status"] in {"time_budget", "actions_budget", "cancelled"}:
            stop = outcomes[-1]["status"]
            break
    complete = len(outcomes) == len(value["candidates"]) and all(row["status"] == "completed" for row in outcomes)
    mode_missing = (["scenario.unbroken_and_broken_windows"] if value["mode"] == "apocalyptic_shadow" and
                    {phase["broken"] for phase in value["scenario"]["phases"]} != {False, True} else [])
    rankable = complete and not unequal and not mode_missing
    ordered = sorted(outcomes, key=lambda row: (-(row["expected_damage"] or 0), row["candidate_id"])) if rankable else []
    best = ordered[0]["expected_damage"] if ordered else None
    winners = [row["candidate_id"] for row in ordered if abs(row["expected_damage"] - best) <= 1e-7] if ordered else []
    data = {"scope": "representative_comparison", "label": "简化比较", "method_version": METHOD,
            "input_fingerprint": digest(value), "mechanics_fingerprint": digest(mechanics()),
            "implementation_fingerprint": implementation_fingerprint(),
            "conditions_fingerprint": digest({key: value[key] for key in ("mode", "game_version", "data_version", "scenario")}),
            "mode": value["mode"], "outcomes": outcomes, "ranking": [row["candidate_id"] for row in ordered] if rankable else None,
            "recommendation_ids": winners, "ranking_permitted": rankable,
            "termination": stop or ("completed" if complete else "incomplete"),
            "uncomputed_candidates": [c["id"] for c in value["candidates"] if c["id"] not in {o["candidate_id"] for o in outcomes}],
            "comparison_scope": "只比较给定候选及其固定策略；不代表全局最优、实际得分或账号抽卡收益",
            "relative_to_first": ({row["candidate_id"]: ((row["expected_damage"] / outcomes[0]["expected_damage"] - 1)
                                      if outcomes[0]["expected_damage"] else None) for row in outcomes} if rankable else None)}
    data["explanation"] = explain(data)
    warnings = [LIMITATION, "血线、击破和减速状态是共同外部情景；不由期望伤害反推真实击杀或自动触发次数",
                "四人面板均为明确假设；只支持E0、普攻6／战技终结技天赋10、未解锁大行迹的指定动作，未验证角色拒绝定量"]
    if unequal:
        warnings.append("已声明投资口径差异；仅作情景对照，不生成排名")
    if mode_missing:
        warnings.append("缺少击破前后共同窗口，暂不生成末日整体推荐")
    observed = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return ToolResult(status="success" if rankable else "partial", data=data,
                      sources=[{"type": "derived", "ref": ref, "observed_at": observed} for ref in value["source_refs"]],
                      versions={"engine": __version__, "rules": METHOD, "data_commit": value["data_version"], "game": value["game_version"]},
                      assumptions=value["assumptions"] + value["scenario"]["omitted"], warnings=warnings,
                      missing_fields=sorted({*mode_missing, *(field for row in outcomes for field in row["missing_fields"])}))
