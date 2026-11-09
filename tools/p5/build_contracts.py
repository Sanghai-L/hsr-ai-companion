"""Generate closed analysis contracts and reproducible, clearly hypothetical examples."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODES = ["memory_of_chaos", "pure_fiction", "apocalyptic_shadow", "anomaly_arbitration"]


def write(name, value):
    path = ROOT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def obj(properties, required=None):
    return {"type": "object", "properties": properties, "required": list(properties) if required is None else required, "additionalProperties": False}


def text(n=200):
    return {"type": "string", "minLength": 1, "maxLength": n}


def number(low, high, integer=False):
    return {"type": "integer" if integer else "number", "minimum": low, "maximum": high}


def array(item, low=0, high=30, unique=False):
    return {"type": "array", "items": item, "minItems": low, "maxItems": high, "uniqueItems": unique}


def contracts():
    member = obj({"character_id": text(50), "form_id": text(80), "level": number(1, 80, True),
                  "atk": {"anyOf": [number(0, 100000), {"type": "null"}]}, "speed": number(1, 500),
                  "speed_precision": {"anyOf": [number(.00001, 10), {"type": "null"}]},
                  "crit_rate": number(0, 1), "crit_damage": number(0, 10), "damage_bonus": number(0, 10),
                  "energy_regen": number(0, 5), "eidolon": {"const": 0}, "major_traces": {"const": False},
                  "rotation": array({"enum": ["basic", "skill"]}, 1, 6),
                  "ultimate_policy": {"enum": ["never", "after_turn_when_ready"]},
                  "equipment_instances": array(text(80), 0, 7, True), "required_mechanisms": array(text(120), 0, 15, True)})
    phase = obj({"until_av": number(.001, 1000), "broken": {"type": "boolean"},
                 "damage_taken_multiplier": number(0, 5), "toughness_available": {"type": "boolean"},
                 "hp_above_half": {"type": "boolean"}, "enemy_slowed": {"type": "boolean"}})
    scenario = obj({"id": text(100), "period": text(100), "kind": {"const": "representative"},
                    "enemy_level": number(1, 200, True), "target_count": number(1, 5, True),
                    "resistance": obj({element: number(-1, .9) for element in ["physical", "fire", "ice", "lightning", "wind", "imaginary"]}),
                    "weaknesses": array({"enum": ["physical", "fire", "ice", "lightning", "wind", "imaginary", "quantum"]}, 0, 7, True),
                    "window_av": number(.001, 1000), "initial_sp": number(0, 10, True), "sp_cap": number(1, 10, True),
                    "initial_energy_fraction": number(0, 1), "phases": array(phase, 1, 2),
                    "threshold_crossings": array(obj({"at_av": number(0, 1000), "count": number(1, 5, True)}), 0, 12),
                    "respawn_policy": {"enum": ["none", "fixed_density"]}, "omitted": array(text(1500), 1, 15)})
    candidate = obj({"id": text(80), "label": text(200), "investment_key": text(200),
                     "origin": {"enum": ["synthetic", "hypothesis"]}, "members": array(member, 4, 4)})
    budget = obj({"max_seconds": number(.000001, 10), "max_actions": number(1, 200, True), "max_candidates": number(1, 4, True)})
    schema = obj({"schema_version": {"const": 1}, "method": {"const": "representative-1"},
                  "mode": {"enum": MODES}, "game_version": text(40), "data_version": text(100),
                  "scenario": scenario, "budget": budget, "candidates": array(candidate, 2, 4),
                  "assumptions": array(text(1500), 1, 20), "source_refs": array(text(2000), 1, 20),
                  "difference_declaration": text(1500)},
                 ["schema_version", "method", "mode", "game_version", "data_version", "scenario", "budget", "candidates", "assumptions", "source_refs"])
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    write("schemas/representative-comparison.schema.json", schema)
    multi = obj({"mode": {"enum": MODES},
                 "roster": obj({"origin": {"const": "explicit_hypothesis"}, "notes": text(1500),
                                "available_character_ids": array(text(50), 4, 100, True),
                                "available_equipment_instances": array(text(80), 0, 700, True)}),
                 "slots": array(obj({"id": text(80), "stage_type": {"enum": ["side", "knight", "king"]}, "request": deepcopy(schema)}), 2, 4),
                 "max_combinations": number(1, 256, True), "max_seconds": number(.000001, 10)})
    write("schemas/multi-team.schema.json", multi)
    sensitivity = obj({"request": deepcopy(schema), "axes": array(obj({"field": text(200),
        "values": array({"type": ["number", "boolean"]}, 2, 3, True)}), 1, 2), "max_seconds": number(.000001, 10)})
    write("schemas/sensitivity.schema.json", sensitivity)


def action(multiplier, target="single", *, sp_cost=0, sp_gain=0, energy_gain=0, energy_cost=0, toughness=30):
    return dict(multiplier=multiplier, target=target, sp_cost=sp_cost, sp_gain=sp_gain,
                energy_gain=energy_gain, energy_cost=energy_cost, toughness=toughness)


def catalog():
    # Facts only, from the locked MIT character library. No copied descriptions or art.
    kits = [("1002", "丹恒", "wind", 100), ("1013", "黑塔", "ice", 110),
            ("1001", "三月七", "ice", 120), ("1105", "娜塔莎", "physical", 90),
            ("1104", "杰帕德", "ice", 100), ("1211", "白露", "lightning", 100),
            ("1203", "罗刹", "imaginary", 100), ("1301", "加拉赫", "fire", 110),
            ("1312", "米沙", "ice", 100), ("1107", "克拉拉", "physical", 110),
            ("1221", "云璃", "physical", 120), ("1109", "虎克", "fire", 120)]
    characters = {}
    for char_id, name, element, cap in kits:
        source = next((ROOT / ".local/upstream/hsr-nous/repo/data/library/characters").glob(char_id + "_*.yaml"))
        characters[char_id + ":base"] = {"name": name, "element": element, "energy_cap": cap,
            "actions": {"basic": action(1, sp_gain=1, energy_gain=20)},
            "supported_mechanisms": ["ordinary_direct", "fixed_speed", "basic_sp_energy"],
            "source_ref": "https://github.com/pzc2004/HSR_Nous/blob/f8935ddb407b297732fbd3c624d55897e3e648b9/" + source.relative_to(ROOT / ".local/upstream/hsr-nous/repo").as_posix(),
            "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "scope": "basic-only when no incoming attacks, burns, ally-target abilities or unmodelled passive triggers; not full kit coverage"}
    characters["1002:base"]["actions"].update(skill=action(2.6, sp_cost=1, energy_gain=30, toughness=60),
        ultimate=action(4, energy_cost=100, energy_gain=5, toughness=90))
    characters["1002:base"]["supported_mechanisms"] += ["skill_direct", "ultimate_slowed_multiplier"]
    characters["1013:base"]["actions"].update(skill=action(1, "all", sp_cost=1, energy_gain=30),
        ultimate=action(2, "all", energy_cost=110, energy_gain=5, toughness=60),
        follow_up=action(.4, "all", energy_gain=5, toughness=15))
    characters["1013:base"]["supported_mechanisms"] += ["skill_high_hp_bonus", "explicit_threshold_followup"]
    value = {"schema_version": 1, "method": "representative-1", "data_version": "released-kit-f8935ddb-p5-1", "supported_game_versions": ["4.6"], "upstream_commit": "f8935ddb407b297732fbd3c624d55897e3e648b9",
             "scope": "E0, basic6 and skill/ultimate/talent10, no major traces; final supplied panels; no equipment effects",
             "characters": characters}
    write("manifests/analysis-mechanics.json", value)


def member(char_id, *, main=False):
    return {"character_id": char_id, "form_id": char_id + ":base", "level": 80,
            "atk": 2000 if main else 1000, "speed": 100, "speed_precision": None,
            "crit_rate": .5 if main else 0, "crit_damage": 1 if main else .5, "damage_bonus": 0,
            "energy_regen": 0, "eidolon": 0, "major_traces": False,
            "rotation": ["skill"] if main else ["basic"], "ultimate_policy": "never",
            "equipment_instances": [], "required_mechanisms": []}


def example(mode="memory_of_chaos"):
    return {"schema_version": 1, "method": "representative-1", "mode": mode, "game_version": "4.6",
            "data_version": "released-kit-f8935ddb-p5-1",
            "scenario": {"id": "alpha-moc-representative-v1", "period": "generic-no-current-claim", "kind": "representative",
                "enemy_level": 80, "target_count": 1, "resistance": {e: 0 for e in ["physical", "fire", "ice", "lightning", "wind", "imaginary"]},
                "weaknesses": ["wind", "ice", "physical"], "window_av": 200, "initial_sp": 3, "sp_cap": 5,
                "initial_energy_fraction": 0,
                "phases": [{"until_av": 200, "broken": False, "damage_taken_multiplier": 1,
                            "toughness_available": True, "hp_above_half": True, "enemy_slowed": False}],
                "threshold_crossings": [], "respawn_policy": "none",
                "omitted": ["省略敌人行动、存活、真实击破和关卡增益；同速按队内顺序行动", "未解锁大行迹、无秘技／主动装备效果、无队友指向增益；不是玩家真实练度", "固定高血线目标；伤害是输出容量，不反推HP、击杀或通关"]},
            "budget": {"max_seconds": 5, "max_actions": 120, "max_candidates": 4},
            "candidates": [{"id": key, "label": label, "investment_key": "assumed-panels-v1", "origin": "hypothesis",
                            "members": [member(char_id, main=True), member("1001"), member("1105"), member("1104")]}
                           for key, label, char_id in [("dan-heng", "丹恒单体＋三人普攻资源位", "1002"), ("herta", "黑塔对群＋三人普攻资源位", "1013")]],
            "assumptions": ["明确的工程假设面板与固定输出窗口；不代表成熟配队推荐，示范单体／对群选择", "血线、弱点和击破窗口是共同外部条件，未做整场游戏内校准"],
            "source_refs": ["https://srl.keqingmains.com/characters/ice/herta", "https://srl.keqingmains.com/characters/wind/dan-heng",
                            "https://srl.keqingmains.com/combat-mechanics/damage/damage-formula",
                            "https://github.com/pzc2004/HSR_Nous/tree/f8935ddb407b297732fbd3c624d55897e3e648b9/data/library/characters"]}


def fixtures():
    for mode, short in zip(MODES, ["moc", "pf", "as", "aa"]):
        value = example(mode)
        value["scenario"]["id"] = f"{short}-representative-v1"
        if short == "pf":
            value["scenario"].update(target_count=5, respawn_policy="fixed_density",
                threshold_crossings=[{"at_av": 110, "count": 1}, {"at_av": 190, "count": 1}])
            value["assumptions"].append("补怪保持5个可攻击目标；AV110和190各一次新目标跨50%血线，黑塔据此追加，不预测实际击杀数")
        if short == "as":
            value["scenario"]["phases"] = [{"until_av": 100, "broken": False, "damage_taken_multiplier": .5,
                "toughness_available": True, "hp_above_half": True, "enemy_slowed": False},
                {"until_av": 200, "broken": True, "damage_taken_multiplier": 2,
                 "toughness_available": False, "hp_above_half": False, "enemy_slowed": False}]
            value["assumptions"].append("假设AV100后进入击破窗口；0.5／2是本次明确模型乘数，不声称任意当前Boss都如此；不计击破／超击破伤害")
        if short == "aa":
            value["scenario"].update(target_count=3)
            value["assumptions"].append("只比较一个骑士目标配置；三骑士／王棋合法编成另由多队分配处理，不推断当期敌人特性")
        write(f"benchmarks/modes/{short}/representative-v1.json", value)
        write(f"src/companion/resources/examples/{short}-comparison.json", {"request": value})
    write("tests/fixtures/requests/comparison.json", {"request": example()})
    write("tests/fixtures/requests/sensitivity.json", {"request": example(),
        "axes": [{"field": "scenario.target_count", "values": [1, 2, 3]}], "max_seconds": 10})
    write("benchmarks/archetypes/catalog.json", {"schema_version": 1, "examples": [
        {"id": "single-target", "case": "benchmarks/modes/moc/representative-v1.json", "mechanism": "丹恒战技单体2.6倍率；每次消耗1战技点，其他三人普攻产点"},
        {"id": "multi-target-threshold", "case": "benchmarks/modes/pf/representative-v1.json", "mechanism": "黑塔战技全体1.0＋高血线20%增伤；给定跨50%血线后全体0.4追加"}],
        "policy": "限定动作及条件，未经支持的新角色不纳入数值排名；面板均为假设，不代表当前meta或全角色覆盖"})


if __name__ == "__main__":
    contracts()
    catalog()
    fixtures()
