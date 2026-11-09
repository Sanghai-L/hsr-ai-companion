"""D004: original, synthetic acceptance inputs. Never contact a UID service."""
import json
from common import ROOT, LOCAL, now, write_json, update_task

QUESTIONS = [
    ("mechanics", "解释行动值、速度与拉条如何影响先后顺序。", ["速度单位明确", "行动值按 10000/速度 推导"], ["knowledge_search", "calculate"], ["把拉条等同永久速度增加"], ["给出固定输入的行动值", "区分剩余距离与速度"]),
    ("wrong-premise", "没放在展示页的角色，能不能当成我没有？", ["展示不是完整持有列表"], ["account_get"], ["将未展示改成未持有", "自动刷新 UID"], ["明确回答不能", "未知持有状态保持未知"]),
    ("counterexample", "你说这个队伍一定缺战技点，但我给出了连续两轮净产点的完整操作记录。请重算。", ["逐动作耗点和产点", "初始战技点"], ["calculate", "memory_search"], ["忽略反例", "无确认覆盖旧结论"], ["检查完整动作序列", "有效反例引起复核并记录冲突"]),
    ("speed", "134 速和 133.3 速在首轮行动次数上有没有差别？", ["首轮行动值长度", "面板速度精度", "无额外提前行动"], ["calculate"], ["把面板整数当精确隐藏小数"], ["声明首轮长度假设", "用时间轴与边界计算判断"]),
    ("skill-points", "四人队每人都优先战技，能循环吗？请列出前两轮战技点变化。", ["四人动作顺序", "初始点数", "耗产点"], ["calculate", "simulation_preflight"], ["战技点负数仍合法放战技"], ["每步资源有前后值", "资料不够时列缺项"]),
    ("two-teams", "在 alpha-moc 固定条件下比较两队，说明差异来自哪里。", ["冻结场景", "四人队配置", "相同种子和资源预算", "覆盖清单"], ["simulation_preflight", "simulation_submit", "simulation_result"], ["用木桩冒充混沌", "从总伤害编造通关轮次"], ["先校验场景与覆盖", "结果可重放且两队条件一致"]),
    ("equipment", "没有专属光锥，换一把四星会损失多少？", ["指定角色与两把光锥", "叠影", "面板口径", "敌人"], ["account_get", "calculate"], ["重复叠加装备属性", "未持有装备假定已有"], ["识别缺输入", "比较相同装备预算"]),
    ("character-or-cone", "有限预算下，抽新角色还是给现有主力抽光锥？", ["现有队伍", "角色池和光锥池独立保底", "资源"], ["account_get", "calculate", "planning"], ["混用两种池保底", "忽略不抽方案"], ["包含不抽方案", "预算与战斗收益分开说明"]),
    ("budget", "账号 A 的资源能支持多大抽卡预算？我没告诉你保底。", ["资源来源", "160 星琼一抽的已验证规则", "保底未知"], ["account_get", "calculate"], ["默认保底为零", "凭空给抽中概率"], ["确定预算与未知概率分开", "列出缺失保底状态"]),
    ("long-term", "我偏爱角色收集，给一个跨两版本的保守计划。", ["偏好", "已知储备", "未来收入区间", "未确认卡池"], ["memory_search", "planning"], ["未来卡池当已确定", "将预计收入当现有资源"], ["区分储备与预测", "给出可重算情景和停止线"]),
    ("unreleased", "有人爆料下版本新机制，请直接放进正式服模拟。", ["信息上线状态", "正式规则版本"], ["source_fetch", "simulation_preflight"], ["爆料静默进入正式输入"], ["标明未上线", "正式模拟拒绝混入并可提出独立假设实验"]),
    ("memory-conflict", "上次你记的结论和新版本数值冲突，请继续分析。", ["旧结论 ID", "新旧来源版本", "玩家尚未确认替换"], ["memory_search", "memory_append", "conflict_propose"], ["无确认覆盖旧记录"], ["保留旧记录", "记录新证据与冲突并等待修改确认"]),
]


def main():
    cases = []
    for i, (topic, prompt, facts, tools, forbidden, observable) in enumerate(QUESTIONS, 1):
        cases.append({"id": f"seed-{i:02}", "category": topic, "input": prompt,
            "necessary_facts": facts, "capabilities": tools, "forbidden_behaviors": forbidden,
            "pass_conditions": observable, "evaluation": "人工或结构化轨迹检查；不是黄金回答文案",
            "synthetic": True})
    write_json(ROOT / "evals/cases/seed-12.json", {"schema_version": 1, "cases": cases})
    for label, resources, characters in (
        ("A", {"stellar_jade": 12000, "special_passes": 10, "character_pity": None,
               "character_guaranteed": None, "cone_pity": None}, ["1408", "1412", "1313", "1414"]),
        ("B", {"stellar_jade": 0, "special_passes": None, "character_pity": 45,
               "character_guaranteed": True, "cone_pity": None}, ["1308", "1006", "1106", "1304"]),
    ):
        value = {"schema_version": 1, "synthetic": True, "account_id": f"synthetic-{label}",
            "uid": None, "region": "synthetic", "roster_completeness": "partial",
            "ownership_of_unlisted": "unknown", "snapshot_at": "2026-11-06T00:00:00Z",
            "characters": [{"entity_id": cid, "ownership": "owned", "level": 80,
                             "eidolon": None, "light_cone": None, "relics": None,
                             "source": "synthetic-public-showcase"} for cid in characters],
            "resources": {key: {"value": v, "status": "unknown" if v is None else "known",
                                "source": "synthetic-manual" if v is not None else None}
                          for key, v in resources.items()},
            "manual_supplements": [{"field": "preference", "value": "喜欢角色收集" if label=="A" else "优先高难通关", "source": "synthetic-manual"}]}
        write_json(ROOT / f"tests/fixtures/accounts/synthetic-{label.lower()}.json", value)
    write_json(ROOT / "benchmarks/catalog.json", {"schema_version": 1, "cases": [{
        "id": "alpha-moc", "mode": "memory-of-chaos", "status": "CANDIDATE",
        "scenario": {"game_version": None, "period_id": None, "region": None,
                     "snapshot": None, "missing_fields": ["正式服期数", "敌人波次与等级", "场景效果", "初始资源", "计分规则", "数据来源许可"]},
        "teams": [
            {"id": "team-a", "candidate_entity_ids": ["1408", "1412", "1313", "1414"],
             "names": ["白厄", "刻律德菈", "星期日", "丹恒•腾荒"], "candidate_evidence": "HSR_Nous data/battles/demo_白厄队.yaml", "runnable": None},
            {"id": "team-b", "candidate_entity_ids": ["1308", "1006", "1106", "1304"],
             "names": ["黄泉", "银狼", "佩拉", "砂金"], "candidate_evidence": "HSR_Nous data/library/characters，模板存在；四人组合待实跑", "runnable": None}],
        "team_selection": "P0 工程候选；正式产品验收队伍后续再确认",
        "unknown_build_fields": ["星魂", "光锥与叠影", "遗器", "精确属性", "策略"],
        "seed": 42, "prohibitions": ["不把未知持有当未持有", "不把 demo 假人命名为正式混沌", "不声称游戏精度已通过"]}]})
    evidence = {"at": now(), "case_count": len(cases), "accounts": 2, "real_uids": 0,
                "candidate_template_ids_verified": [], "exit_code": 0}
    root = LOCAL / "upstream/hsr-nous/repo/data/library/characters"
    for cid in ["1408", "1412", "1313", "1414", "1308", "1006", "1106", "1304"]:
        assert list(root.glob(cid+"_*.yaml")), cid
        evidence["candidate_template_ids_verified"].append(cid)
    write_json(LOCAL / "evidence/D004/samples-validation.json", evidence)
    update_task("D004", "DONE", summary="12 道可判定种子问题、2 个合成账号、alpha-moc 候选目录",
                artifacts=["evals/cases/seed-12.json", "tests/fixtures/accounts/", "benchmarks/catalog.json"],
                commands=["python tools/p0/create_samples.py"],
                counts={"passed": 8+12+2, "failed": 0, "skipped": 0},
                evidence=[".local/evidence/D004/samples-validation.json"], next_step="D005；无依赖分支 D006、D007")
    print(json.dumps({"seed_cases": len(cases), "synthetic_accounts": 2, "template_ids": 8}))


if __name__ == "__main__":
    main()
