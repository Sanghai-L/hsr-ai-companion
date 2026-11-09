"""Declare observed coverage; no template-count-based support inference."""
from record import ROOT, write_json
import json


def main():
    entries = []

    def add(key, status, reason, impact, cases, executable=True):
        entries.append({"key": key, "status": status, "reason": reason, "impact": impact,
                        "validation_cases": cases, "model_executable": executable, "critical": True})

    for cid, path in (("1408", "Warrior"), ("1412", "Shaman"), ("1313", "Shaman"), ("1414", "Knight"),
                      ("1308", "Warlock"), ("1006", "Warlock"), ("1106", "Warlock"), ("1304", "Knight")):
        for key in (f"character:{cid}:base", f"eidolon:{cid}:0", f"traces:{cid}:all_unlocked"):
            add(key, "approximate", "锁定模板实际执行；角色 caveats 与历史规则未逐项游戏核验",
                "可能改变伤害、行动、资源及队伍排序", ["tests/simulation/test_backend_adapter.py", "docs/feasibility/simulator-probe.md"])
    for eid in ("3013010", "1023020", "3024020"):
        add(f"enemy:{eid}:stats", "approximate", "D038场景适配已将hard=3/elite=164数值绑定到真实编译对象；尚无完整游戏条件校准",
            "来源数值核对通过仍不能排除历史版本或游戏机制误差", ["tests/modes/test_moc.py", "benchmarks/modes/moc/README.md"])
        add(f"enemy:{eid}:resistance", "approximate", "D038显式导入冻结元素抗性；特殊减伤和阶段联动仍缺失",
            "基础抗性已绑定，但特殊阶段仍可能改变元素收益与排名", ["tests/modes/test_moc.py", "benchmarks/modes/moc/README.md"])
        add(f"enemy:{eid}:ai", "unsupported", "敌方只有占位动作；没有完整出招／控制／召唤逻辑",
            "生存、受击回能与资源无法预测", ["docs/feasibility/simulator-probe.md"])
        add(f"enemy:{eid}:phase", "unsupported", "缺少首个场景的敌人阶段与特殊减伤／资源联动",
            "通关可行性与比较可能改变", ["docs/feasibility/simulator-probe.md"])
    for system in ("action_order", "skill_points", "energy", "critical_roll", "direct_damage", "break", "death", "wave_transition", "cycle_boundary"):
        add(f"system:{system}", "approximate", "核心相关测试及两队固定种子工程执行，未获整场客户端精度资格",
            "模型内复现不能排除系统误差", ["tests/simulation/test_backend_adapter.py", "docs/feasibility/simulator-probe.md"])
    add("scenario:alpha-moc:lineup", "verified", "冻结历史4.4.1/1034/12上半编成；不是当前关卡声明",
        "只证明编成来源，不证明全场机制", ["benchmarks/catalog.json"])
    add("scenario:alpha-moc:historical_rules", "approximate", "使用锁定较新模板运行历史编成；不等于还原全部4.4规则",
        "跨版本差异可能改变队伍收益", ["benchmarks/catalog.json"])
    add("scenario:alpha-moc:turbulence:inactive", "verified", "该增益只选巡猎／智识；已冻结候选没有符合命途的角色",
        "只适用于当前八名候选；改队须重检", ["benchmarks/catalog.json"])
    add("scenario:alpha-moc:turbulence:active", "unsupported", "需要立即行动和增伤的关卡效果尚未接线",
        "行动顺序与收益改变", ["benchmarks/catalog.json"], executable=False)
    add("system:techniques", "unknown", "秘技顺序与初始资源缺乏已对齐的场景输入",
        "开局资源与阶段可能改变", ["benchmarks/catalog.json"], executable=False)
    catalog = json.loads((ROOT / "benchmarks/catalog.json").read_bytes())["cases"][0]
    write_json("manifests/coverage.json", {"schema_version": 1, "backend_commit": "f8935ddb407b297732fbd3c624d55897e3e648b9",
               "game_accuracy_certified": False,
               "character_paths": dict((cid + ":base", path) for cid, path in (("1408", "Warrior"), ("1412", "Shaman"), ("1313", "Shaman"), ("1414", "Knight"), ("1308", "Warlock"), ("1006", "Warlock"), ("1106", "Warlock"), ("1304", "Knight"))),
               "scenarios": {"alpha-moc": {"enemy_ids": ["3013010", "1023020", "3024020"],
                             "game_version": "4.4", "period": "4.4.1", "source_snapshot_sha256": catalog["scenario"]["sha256"]}}, "entries": entries})
    print("Declared", len(entries), "coverage entries with explicit limitations")


if __name__ == "__main__":
    main()
