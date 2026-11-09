"""Explanations refer only to measured projection outputs."""


def explain(result):
    reports = []
    for row in result["outcomes"]:
        if row["expected_damage"] is None:
            reports.append({"candidate_id": row["candidate_id"], "reason": row["reason"], "missing_fields": row["missing_fields"]})
            continue
        reports.append({"candidate_id": row["candidate_id"], "expected_damage": row["expected_damage"],
                        "contributions": row["damage_by_actor"], "action_counts": row["action_counts"],
                        "resource_deficits": row["deficits"], "final_sp": row["final_sp"],
                        "note": "来自实际计算的技能次数、单体／群体倍率和资源限制；未推断敌人行动或实战必胜"})
    return {"reports": reports, "recommendation_scope": result["comparison_scope"],
            "ranking_reason": "全部候选同条件且完整计算" if result["ranking_permitted"] else "存在缺项、预算终止或投资口径差异，暂不排名"}
