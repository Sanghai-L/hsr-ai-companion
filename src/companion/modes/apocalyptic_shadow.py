"""Two supplied break windows; no Boss AI or inferred precise score."""
from .analysis import finish


def analyze(request=None):
    guidance = ["先确认弱点、锁韧／转移弱点和可攻击条件；原始伤害高不等于能及时打开击破窗口",
                "击破前准备SP与能量，击破后集中主要输出；窗口由本次场景明确给出，不从输出容量推测实际击破时刻",
                "削韧使用旧30单位口径；只统计弱点匹配的容量，击破／超击破伤害与真实韧性条转换未支持"]
    result = finish("apocalyptic_shadow", request, guidance,
                    quantitative_scope="击破前后两个外部参数窗口的普通直伤、削韧容量与资源准备",
                    extra={"phase_inputs": request["scenario"]["phases"] if request else [], "game_score": None})
    if request is not None:
        result.data["mode_details"]["window_results"] = [{"candidate_id": row["candidate_id"],
            "damage_by_phase": row.get("damage_by_phase"), "resources_by_phase": row.get("resources_by_phase")}
            for row in result.data["outcomes"]]
        phases = request["scenario"]["phases"]
        if {phase["broken"] for phase in phases} != {False, True}:
            result.status = "partial"
            result.data["ranking"] = None
            result.data["ranking_permitted"] = False
            result.data["recommendation_ids"] = []
            result.data["relative_to_first"] = None
            result.data["explanation"]["ranking_reason"] = "缺少击破前后共同窗口，仅作局部分析"
            result.missing_fields.append("scenario.unbroken_and_broken_windows")
            result.warnings.append("未同时提供击破前后窗口；只能给局部输出，不生成末日整体推荐")
    return result
