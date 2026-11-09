"""Fixed target density and explicit threshold opportunities, never game points."""
from .analysis import finish


def analyze(request=None):
    guidance = ["先核对本期敌人密度与可选增益，再比较对群覆盖和持续产点；不要只比较单体峰值",
                "黑塔只有敌人跨越50%血线才有追加机会；补怪与击杀频率会改变结论，不能按每次攻击默认触发",
                "保留清理残血和终结技窗口；模型不包含狂热值、真实补怪顺序或精确计分"]
    extra = {} if request is None else {"target_slots": request["scenario"]["target_count"],
        "respawn_assumption": request["scenario"]["respawn_policy"],
        "threshold_opportunities": request["scenario"]["threshold_crossings"], "game_points": None}
    return finish("pure_fiction", request, guidance, quantitative_scope="固定目标密度下的群体直伤、跨血线追加和SP循环", extra=extra)
