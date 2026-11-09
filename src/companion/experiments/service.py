"""One versioned entry for CLI/MCP quantitative tools, always read-only."""
import hashlib
from datetime import datetime, timezone
from companion.contracts import CompanionError, ErrorCode, ToolResult, canonical
from .contracts import fingerprint, prepare


def execute(experiment, *, planning_only=False):
    value = prepare(experiment)
    kind = value["kind"]
    if planning_only and kind != "pull_plan":
        raise CompanionError(ErrorCode.INVALID_INPUT, "plan_pulls 需要 pull_plan 实验")
    if kind == "damage":
        from companion.calculators.damage import calculate
        data = calculate(value["parameters"])
    elif kind == "timeline":
        from companion.calculators.timeline import calculate
        data = calculate(value["parameters"], value["budget"])
    elif kind == "gacha":
        from companion.calculators.gacha import calculate
        data = calculate(value["parameters"], value["budget"])
    elif kind == "pull_plan":
        from companion.planning.pulls import calculate
        data = calculate(value["parameters"], value["budget"])
    else:
        raise CompanionError(ErrorCode.UNSUPPORTED, "完整战斗模拟属于 P4；当前未交付")
    warnings, missing = [], []
    status = "success"
    if kind == "damage":
        warnings.append("固定状态普通直伤；来源交叉核对及手算通过，不等于整场收益或游戏内校准")
    if kind == "timeline":
        warnings.append("局部行动／资源分析；不包含敌人、增益持续时间、召唤物或特殊资源")
        if data["termination"] != "horizon":
            status = "partial"
            warnings.append("时序终止原因：" + data["termination"])
        if data["termination"] == "insufficient_speed_precision":
            missing = ["parameters.actors.exact_speed_or_explicit_scenario"]
    if kind == "gacha":
        if data["rules"]["curve_kind"] != "synthetic":
            warnings.append("逐抽概率为明确假设；官方基础率与硬保底不能唯一确定软保底曲线，不是官方精确概率")
        if data["state_unknown"]:
            status = "partial"
            warnings.append("初始保底／保证状态未知；仅给可能范围，不猜测状态或平均值")
            missing = ["parameters.state." + k for k in ("pity", "guaranteed") if value["parameters"]["state"][k] is None]
    if kind == "pull_plan":
        warnings.append("预算和偏好由玩家提供；不读 UID；抽取可达性与战斗收益分开，包含不抽方案")
        for option in data["options"]:
            if option["status"] != "calculated":
                status = "partial"
                missing.extend(option.get("missing_fields", []))
        if any(option.get("schedule_assumption") for option in data["options"]):
            warnings.append("日期含玩家明确假设，不代表官方未来卡池安排")
        warnings.append("真实卡池逐抽曲线如标为 empirical_assumption／explicit_assumption，只是概率情景")
    sources = list(value["source_refs"])
    if kind == "damage":
        sources.append("https://srl.keqingmains.com/combat-mechanics/damage/damage-formula")
    if kind == "timeline":
        sources.append("https://hsr.keqingmains.com/misc/speed-guide/")
        sources.append("https://hsr.keqingmains.com/wp-content/uploads/2024/01/KQM_Bronya_Guide_SPD_Formula_Proofs.pdf")
    if kind == "gacha":
        sources.extend(data["rules"]["source_refs"])
    if kind == "pull_plan":
        from companion.calculators.gacha import resolve_rules
        sources.extend(ref for option in value["parameters"]["options"] for stage in option["stages"] for ref in resolve_rules(stage["rules"])["source_refs"])
    observed_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return ToolResult(status=status, data={"experiment_fingerprint": fingerprint(value), "input": {k: v for k, v in value.items() if k != "run"},
                                          "result": data, "result_fingerprint": hashlib.sha256(canonical(data)).hexdigest()},
                      sources=[{"type": "derived", "ref": ref, "observed_at": observed_at} for ref in dict.fromkeys(sources)],
                      versions={"game": value["conditions"]["game_version"], "engine": value["versions"]["engine"],
                                "rules": value["versions"]["rules"], "knowledge": value["versions"]["knowledge"],
                                "data_commit": value["versions"]["data"]},
                      assumptions=value["assumptions"], warnings=warnings,
                      missing_fields=sorted(set(missing)))
