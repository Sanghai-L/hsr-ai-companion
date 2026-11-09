"""Mode selection and contract discovery do not require reading development files."""
from copy import deepcopy
import json

from companion.contracts import CompanionError, ErrorCode, ToolResult
from companion.resources import resource_text
from companion.simulation.rotation import mechanics

MODES = {"memory_of_chaos": ("混沌回忆", "moc"), "pure_fiction": ("虚构叙事", "pf"),
         "apocalyptic_shadow": ("末日幻影", "as"), "anomaly_arbitration": ("异相仲裁", "aa")}
ALIASES = dict(zip(MODES, ["混沌", "虚构", "末日", "仲裁"]))
MODE_SOURCES = {"memory_of_chaos": ["https://www.hoyolab.com/article/42166551"],
                "pure_fiction": ["https://wiki.biligame.com/sr/虚构叙事", "https://srl.keqingmains.com/characters/ice/herta"],
                "apocalyptic_shadow": ["https://www.hoyolab.com/article/42166551"],
                "anomaly_arbitration": ["https://wiki.biligame.com/sr/异相仲裁", "https://honkai-star-rail.fandom.com/wiki/Anomaly_Arbitration"]}


def select_mode(query):
    text = query.lower().replace(" ", "").replace("-", "_")
    matches = [key for key, (name, short) in MODES.items()
               if name in text or ALIASES[key] in text or key.replace("_", "") in text or text == short]
    if len(matches) != 1:
        return ToolResult(status="partial", data={"selected_mode": None, "matches": matches, "choices": MODES},
                          missing_fields=["mode"], warnings=["模式未确定或同时提到多个模式；请明确要分析哪种玩法"])
    return ToolResult(data={"selected_mode": matches[0], "name": MODES[matches[0]][0], "next_operation": "analysis_schema"})


def schema(mode="memory_of_chaos"):
    if mode not in MODES:
        raise CompanionError(ErrorCode.UNSUPPORTED, "未支持的模式")
    value = json.loads(resource_text("schemas", "representative-comparison.schema.json"))
    example = json.loads(resource_text("examples", MODES[mode][1] + "-comparison.json"))
    return ToolResult(data={"mode": mode, "request_schema": value, "example_request": example,
                           "mechanism_scope": deepcopy(mechanics()),
                           "operations": ["mode_analyze", "simulation_compare", "comparison_save", "experiment_replay", "multi_team_plan", "sensitivity_analyze", "current_stage_check"],
                           "example_policy": "有来源的指定技能＋明确假设面板，不是玩家持有或练度；不代表真实关卡复刻"})


def analyze(mode, request=None):
    from . import pure_fiction, apocalyptic_shadow, anomaly_arbitration
    if mode not in MODES:
        raise CompanionError(ErrorCode.UNSUPPORTED, "未支持的模式")
    if request is not None and request.get("mode") != mode:
        raise CompanionError(ErrorCode.INVALID_INPUT, "请求模式与所选模板不一致")
    if mode == "memory_of_chaos":
        from .memory_of_chaos import analyze_representative
        return analyze_representative(request)
    return {"pure_fiction": pure_fiction, "apocalyptic_shadow": apocalyptic_shadow,
            "anomaly_arbitration": anomaly_arbitration}[mode].analyze(request)


def finish(mode, request, guidance, *, quantitative_scope, extra=None):
    from datetime import datetime, timezone
    sources = [{"type": "derived", "ref": ref, "observed_at": datetime.now(timezone.utc).isoformat(timespec="seconds")} for ref in MODE_SOURCES[mode]]
    if request is None:
        return ToolResult(status="partial", data={"mode": mode, "analysis_kind": "qualitative", "guidance": guidance,
                                                   "comparison": None, "scope": quantitative_scope, "current_period_confirmed": False}, sources=sources,
                          missing_fields=["request.scenario", "request.candidates"],
                          warnings=["未提供必要条件；仅返回策略方向，不能编造数值或当前关卡增益"])
    from companion.simulation.compare import compare
    result = compare(request)
    result.sources.extend(source for source in sources if source["ref"] not in {s["ref"] for s in result.sources})
    result.data.update(analysis_kind="conditional_quantitative", guidance=guidance,
                       mode_scope=quantitative_scope, mode_details=extra or {})
    return result
