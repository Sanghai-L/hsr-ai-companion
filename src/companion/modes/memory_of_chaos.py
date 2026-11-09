"""Historical MoC source adapter. Complete-scene requests fail on missing AI.

Stat conversion is useful independently of AI implementation. Returning a
diagnostic stage does not confer a complete-scenario or game-accuracy label.
"""
from decimal import Decimal
import hashlib
import json
from pathlib import Path

from companion.contracts import CompanionError, ErrorCode
from companion.resources import resource_text
from companion.simulation.builds import to_backend_build
from companion.sim_backends.base import BackendInput

ELEMENTS = ("physical", "fire", "ice", "thunder", "wind", "quantum", "imaginary")


def scalar(value, *, field):
    if isinstance(value, dict):
        value = value.get("Value")
    if value is None or isinstance(value, bool):
        raise CompanionError(ErrorCode.MISSING_DATA, "冻结敌人数值缺失", details={"fields": [field]})
    result = Decimal(str(value))
    if not result.is_finite():
        raise CompanionError(ErrorCode.INVALID_INPUT, "敌人数值不是有限数")
    return result


def enemy_stats(instance, template, hard, elite, *, level):
    """Base × stage-level group × stage-elite group × instance modifier.

    The stage chooses hard/elite groups. Instance default groups must never
    replace them. Only documented optional additive adjustments default to 0.
    """
    result = {}
    for output, base, ratio, modify in (("hp", "HPBase", "HPRatio", "HPModifyRatio"),
             ("atk", "AttackBase", "AttackRatio", "AttackModifyRatio"),
             ("def_", "DefenceBase", "DefenceRatio", "DefenceModifyRatio"),
             ("spd", "SpeedBase", "SpeedRatio", "SpeedModifyRatio"),
             ("max_toughness", "StanceBase", "StanceRatio", "StanceModifyRatio")):
        result[output] = float(scalar(template.get(base), field=base) * scalar(hard.get(ratio), field="hard." + ratio)
                               * scalar(elite.get(ratio), field="elite." + ratio) * scalar(instance.get(modify), field=modify))
    for output, source in (("spd", "SpeedModifyValue"), ("max_toughness", "StanceModifyValue")):
        result[output] += float(scalar(instance.get(source, 0), field=source) + scalar(template.get(source, 0), field=source))
    result["effect_res"] = float(scalar(template.get("StatusResistanceBase"), field="StatusResistanceBase")
                                  + max(Decimal(0), min(Decimal("0.1"), Decimal(level - 50) * Decimal("0.004"))))
    # Sparse resistance list: omitted elements are zero, as defined by this
    # source format. Entirely absent field is unknown, not an all-zero list.
    if "DamageTypeResistance" not in instance or not isinstance(instance["DamageTypeResistance"], list):
        raise CompanionError(ErrorCode.MISSING_DATA, "冻结敌人抗性字段缺失", details={"fields": ["DamageTypeResistance"]})
    resistance = dict.fromkeys(ELEMENTS, 0.0)
    seen = set()
    for item in instance["DamageTypeResistance"]:
        element = item["DamageType"].lower()
        if element not in resistance or element in seen:
            raise CompanionError(ErrorCode.INVALID_INPUT, "敌人抗性元素未知或重复")
        seen.add(element)
        resistance[element] = float(scalar(item.get("Value"), field="resistance." + element))
    result["resistance"] = resistance
    return result


def outcome(termination, *, truncated=False):
    if truncated:
        return {"outcome": "incomplete", "victory": False, "reason": "engine_safety_limit"}
    if termination == "target_killed":
        return {"outcome": "victory", "victory": True, "reason": termination}
    if termination == "all_allies_dead":
        return {"outcome": "defeat", "victory": False, "reason": termination}
    if termination in {"max_action_value_reached", "max_cycles"}:
        return {"outcome": "timeout", "victory": False, "reason": termination}
    return {"outcome": "incomplete", "victory": False, "reason": termination}


class FrozenMoc:
    def __init__(self, scenario_path, data_path):
        raw = Path(scenario_path).read_bytes()
        coverage = json.loads(resource_text("manifests", "coverage.json"))
        expected = coverage["scenarios"]["alpha-moc"]["source_snapshot_sha256"]
        if hashlib.sha256(raw).hexdigest() != expected:
            raise CompanionError(ErrorCode.VERSION_INCOMPATIBLE, "历史场景快照与冻结指纹不一致")
        self.scenario = json.loads(raw)
        self.data = Path(data_path)
        self.source_sha256 = expected
        self.coverage = coverage

    def inspect(self):
        scenario = self.scenario
        tables = {name: json.loads((self.data / "turnbasedgamedata" / (name + ".json")).read_bytes())
                  for name in ("MonsterConfig", "MonsterTemplateConfig", "MonsterSkillConfig", "HardLevelGroup", "EliteGroup")}
        # Check the exact files consumed here, independent of backend launch.
        lock = json.loads(resource_text("manifests", "simulator.lock.json"))
        for item in lock["content_locks"]:
            if item["root"] == "data":
                if hashlib.sha256((self.data / item["path"]).read_bytes()).hexdigest() != item["sha256"]:
                    raise CompanionError(ErrorCode.VERSION_INCOMPATIBLE, "场景数值来源与程序锁不一致")
        instances = {str(r["MonsterID"]): r for r in tables["MonsterConfig"]}
        templates = {str(r["MonsterTemplateID"]): r for r in tables["MonsterTemplateConfig"]}
        hard = next((r for r in tables["HardLevelGroup"] if r["HardLevelGroup"] == scenario["hard_level_group"] and r["Level"] == scenario["enemy_level"]), None)
        elite = next((r for r in tables["EliteGroup"] if r["EliteGroup"] == scenario["elite_group"]), None)
        if hard is None or elite is None:
            raise CompanionError(ErrorCode.MISSING_DATA, "冻结场景指定的等级／精英系数缺失")
        audit, overrides = [], {}
        for wave in scenario["waves"]:
            for position, eid in enumerate(wave["monster_instance_ids"]):
                instance = instances[eid]
                template = templates[str(instance["MonsterTemplateID"])]
                actor_id = f"w{wave['index']}_{position}_{eid}"
                stats = enemy_stats(instance, template, hard, elite, level=scenario["enemy_level"])
                overrides[actor_id] = stats
                ai_path = instance.get("OverrideAIPath") or template.get("AIPath")
                audit.append({"enemy_id": eid, "actor_id": actor_id, "wave": wave["index"], "stats": stats,
                              "instance_groups": {"hard": instance.get("HardLevelGroup"), "elite": instance.get("EliteGroup")},
                              "used_stage_groups": {"hard": scenario["hard_level_group"], "elite": scenario["elite_group"]},
                              "ai_path_reference": ai_path, "ai_behavior_file_present": bool(ai_path and (self.data / ai_path).is_file()),
                              "complete_ai_executed": False, "complete_phase_executed": False})
        return {"scenario_id": "alpha-moc", "game_version": scenario["game_version"], "period": scenario["period_key"],
                "source_sha256": self.source_sha256, "enemy_audit": audit, "enemy_overrides": overrides,
                "complete_supported": False, "game_accuracy_certified": False,
                "blockers": ["SIM-003:三种敌人的完整AI／控制／召唤／受击回能未执行",
                             "SIM-003:萨姆燃烧战技点、熔火能量、减治疗与阶段切换未执行",
                             "SIM-006:角色caveats尚未逐项核验", "SIM-007:外部完整条件校准缺失"],
                "bounded_fixes": ["关卡指定hard=3/elite=164数值转换", "显式按元素导入抗性"],
                "side": "upper", "full_stage_stars_available": False}

    def backend_input(self, experiment, *, model_diagnostic=False):
        from companion.simulation.preflight import preflight
        report = self.inspect()
        if not model_diagnostic or experiment["parameters"]["precision"] != "model_diagnostic":
            raise CompanionError(ErrorCode.UNSUPPORTED, "首个场景缺少完整敌人机制，不能编译为完整关卡", details={"blockers": report["blockers"]})
        gate = preflight(experiment)
        if gate.status == "error" or not gate.data["can_execute_model_diagnostic"]:
            raise CompanionError(ErrorCode.UNSUPPORTED, "构筑未通过工程诊断预检")
        parameters = experiment["parameters"]
        if parameters["initial_resources"]["techniques"]:
            raise CompanionError(ErrorCode.UNSUPPORTED, "秘技尚未在此冻结场景验证")
        waves = []
        for wave in self.scenario["waves"]:
            enemies = [{"enemy_template": eid, "actor_id": f"w{wave['index']}_{position}_{eid}", "level": self.scenario["enemy_level"]}
                       for position, eid in enumerate(wave["monster_instance_ids"])]
            waves.append({"wave_index": wave["index"], "enemies": enemies})
        stage = {"stage": {"stage_id": "alpha-moc-4.4.1-12-upper-INCOMPLETE-MODEL", "mode": "forgotten_hall",
                           "enemies": waves[0]["enemies"], "waves": waves[1:],
                           "termination": {"mode": "fixed_av", "max_action_value": experiment["budget"]["max_av"]}}}
        return BackendInput(build=to_backend_build(parameters["build"], parameters["policy"]), stage=stage,
                            seed=parameters["seed"], mode=parameters["mode"], initial_sp=parameters["initial_resources"]["skill_points"],
                            initial_energy_ratio=parameters["initial_resources"]["energy_ratio"], enemy_overrides=report["enemy_overrides"])
def analyze_representative(request=None):
    from .analysis import finish
    return finish("memory_of_chaos", request,
                  ["优先比较关键目标与总输出，再核对战技点和主要行动次数", "上下半分别匹配弱点并分配辅助；固定窗口伤害不能换算为精确轮次或必胜"],
                  quantitative_scope="代表性敌人与共同固定AV窗口的两队／配置直伤和资源比较")

