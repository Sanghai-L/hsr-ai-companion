"""Fixed-window offensive projections. Enemy scripts and scores are outside scope."""
from collections import Counter
from copy import deepcopy
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path

from companion.calculators.damage import settle
from companion.calculators.resources import transact
from companion.contracts import CompanionError, ErrorCode, canonical
from companion.experiments.contracts import check, normalize
from companion.jobs import StopCalculation
from companion.resources import resource_text

METHOD = "representative-1"
LIMITATION = "简化固定窗口的条件化输出；不含敌人AI、生存、真实补怪或精确通关轮次／分数／概率"


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def implementation_fingerprint():
    root = Path(__file__).resolve().parents[1]
    return digest({path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                   for path in sorted(root.rglob("*.py")) if "__pycache__" not in path.parts})


@lru_cache(maxsize=1)
def mechanics():
    return json.loads(resource_text("manifests", "analysis-mechanics.json"))


def prepare(request):
    check("representative-comparison.schema.json", request)
    value = normalize(deepcopy(request))
    scenario = value["scenario"]
    if scenario["initial_sp"] > scenario["sp_cap"]:
        raise CompanionError(ErrorCode.INVALID_INPUT, "初始战技点超过上限")
    ends = [phase["until_av"] for phase in scenario["phases"]]
    if ends != sorted(set(ends)) or ends[-1] != scenario["window_av"]:
        raise CompanionError(ErrorCode.INVALID_INPUT, "阶段窗口必须递增并覆盖完整比较时间窗")
    ids = [candidate["id"] for candidate in value["candidates"]]
    if len(ids) != len(set(ids)):
        raise CompanionError(ErrorCode.CONFLICT, "候选编号重复")
    for event in scenario["threshold_crossings"]:
        if event["at_av"] > scenario["window_av"]:
            raise CompanionError(ErrorCode.INVALID_INPUT, "血线跨越假设超出时间窗")
    for candidate in value["candidates"]:
        characters, instances = set(), set()
        for member in candidate["members"]:
            if member["character_id"] in characters:
                raise CompanionError(ErrorCode.CONFLICT, "同一队不能使用同一角色的多个形态")
            if not member["form_id"].startswith(member["character_id"] + ":"):
                raise CompanionError(ErrorCode.INVALID_INPUT, "角色与形态不匹配")
            characters.add(member["character_id"])
            for instance in member["equipment_instances"]:
                if instance in instances:
                    raise CompanionError(ErrorCode.CONFLICT, "同一装备实例被队内重复使用")
                instances.add(instance)
    if value["data_version"] != mechanics()["data_version"] or value["game_version"] not in mechanics()["supported_game_versions"]:
        raise CompanionError(ErrorCode.VERSION_INCOMPATIBLE, "本地技能快照尚未核验该数据／游戏版本")
    return value


def preflight_candidate(candidate, scenario):
    catalog = mechanics()["characters"]
    missing = []
    for member in candidate["members"]:
        form = member["form_id"]
        kit = catalog.get(form)
        if kit is None:
            missing.append(form + ":verified_kit")
            continue
        for action in member["rotation"]:
            if action not in kit["actions"]:
                missing.append(form + ":" + action)
        if member["ultimate_policy"] == "after_turn_when_ready" and "ultimate" not in kit["actions"]:
            missing.append(form + ":ultimate")
        for required in member["required_mechanisms"]:
            if required not in kit["supported_mechanisms"]:
                missing.append(form + ":" + required)
        if member["atk"] is None:
            missing.append(form + ":atk")
        if member["speed_precision"] is not None:
            missing.append(form + ":exact_speed_or_explicit_scenario")
        if form == "1312:base" and any("skill" in m["rotation"] for m in candidate["members"]):
            missing.append(form + ":sp_triggered_talent_energy")
        if form == "1221:base" and (scenario["initial_energy_fraction"] > 0 or
                int(scenario["window_av"] * member["speed"] / 10000) * 20 > 120):
            missing.append(form + ":overflow_energy_capacity")
    return sorted(set(missing))


def project(candidate, scenario, work):
    missing = preflight_candidate(candidate, scenario)
    if missing:
        return {"candidate_id": candidate["id"], "status": "unsupported", "missing_fields": missing,
                "expected_damage": None, "reason": "关键机制或必要数值缺失，不把缺失贡献计为零"}
    actors = deepcopy(candidate["members"])
    shared = {"sp": scenario["initial_sp"], "sp_cap": scenario["sp_cap"]}
    for actor in actors:
        kit = mechanics()["characters"][actor["form_id"]]
        actor.update(energy_cap=kit["energy_cap"], energy=kit["energy_cap"] * scenario["initial_energy_fraction"],
                     next_av=10000 / actor["speed"], turn=0)
    events, crossings = [], sorted(scenario["threshold_crossings"], key=lambda e: e["at_av"])
    counts = Counter()
    damage_by_actor = Counter()
    toughness_by_element = Counter()
    damage_by_phase = Counter()
    resources_by_phase = {}
    deficits = []
    termination = "completed"

    def phase_at(at):
        return next(phase for phase in scenario["phases"] if at <= phase["until_av"] + 1e-9)

    def execute(actor, action_name, at, *, is_turn=False):
        work.checkpoint("actions")
        kit = mechanics()["characters"][actor["form_id"]]
        action = deepcopy(kit["actions"][action_name])
        phase = phase_at(at)
        resource = transact(actor, shared, {**action, "kind": action_name, "regen_applies": True})
        if not resource["executed"]:
            deficits.append({"actor": actor["form_id"], "action": action_name, "at_av": at, **resource["deficits"]})
            return False
        target_count = scenario["target_count"] if action["target"] == "all" else 1
        bonus = actor["damage_bonus"]
        multiplier = action["multiplier"]
        if actor["form_id"] == "1013:base" and action_name == "skill" and phase["hp_above_half"]:
            bonus += .2  # No major traces: Efficiency +25% is deliberately not unlocked.
        if actor["form_id"] == "1002:base" and action_name == "ultimate" and phase["enemy_slowed"]:
            multiplier += 1.2
        params = {"damage_type": "direct", "stat": {"value": actor["atk"], "unit": "flat", "basis": "public_panel", "equipment_bonus": 0},
                  "multiplier": multiplier, "flat_damage": 0, "attacker_level": actor["level"], "enemy_level": scenario["enemy_level"],
                  "damage_bonus": bonus, "def_reduction": 0, "def_ignore": 0,
                  "resistance": scenario["resistance"][kit["element"]], "res_penetration": 0, "vulnerability": 0,
                  "crit_rate": actor["crit_rate"], "crit_damage": actor["crit_damage"], "crit_mode": "expected", "broken": phase["broken"]}
        per_target = settle(params)["value"] * phase["damage_taken_multiplier"]
        amount = per_target * target_count
        toughness = action["toughness"] * target_count if kit["element"] in scenario["weaknesses"] and phase["toughness_available"] else 0
        damage_by_actor[actor["form_id"]] += amount
        phase_index = str(scenario["phases"].index(phase))
        damage_by_phase[phase_index] += amount
        resources_by_phase[phase_index] = {"sp": shared["sp"], "energy": {a["form_id"]: a["energy"] for a in actors}}
        toughness_by_element[kit["element"]] += toughness
        counts[actor["form_id"] + ":" + action_name] += 1
        events.append({"at_av": round(at, 9), "actor": actor["form_id"], "action": action_name,
                       "targets": target_count, "expected_damage": amount, "primary_damage": per_target,
                       "toughness_capacity": toughness, "sp": shared["sp"], "energy": actor["energy"],
                       "sp_overflow": resource["overflow"]["sp"], "energy_overflow": resource["overflow"]["energy"]})
        if is_turn:
            actor["turn"] += 1
            actor["next_av"] = (actor["turn"] + 1) * 10000 / actor["speed"]
        return True

    try:
        while True:
            work.checkpoint()
            actor = min(enumerate(actors), key=lambda item: (item[1]["next_av"], item[0]))[1]
            crossing = crossings[0]["at_av"] if crossings else math.inf
            at = min(actor["next_av"], crossing)
            if at > scenario["window_av"] + 1e-9:
                break
            if crossing <= actor["next_av"]:
                event = crossings.pop(0)
                for herta in (a for a in actors if a["form_id"] == "1013:base"):
                    for _ in range(event["count"]):
                        execute(herta, "follow_up", at)
                continue
            if not execute(actor, actor["rotation"][actor["turn"] % len(actor["rotation"])], at, is_turn=True):
                termination = "resource_deficit"
                break
            if actor["ultimate_policy"] == "after_turn_when_ready" and actor["energy"] >= actor["energy_cap"] - 1e-9:
                execute(actor, "ultimate", at)
    except StopCalculation as stopped:
        termination = stopped.reason
    return {"candidate_id": candidate["id"], "status": termination, "missing_fields": [],
            "expected_damage": math.fsum(damage_by_actor.values()),
            "primary_damage": math.fsum(event["primary_damage"] for event in events),
            "damage_by_actor": dict(damage_by_actor), "action_counts": dict(counts),
            "damage_by_phase": dict(damage_by_phase), "resources_by_phase": resources_by_phase,
            "toughness_capacity_by_element": dict(toughness_by_element),
            "final_sp": shared["sp"], "final_energy": {a["form_id"]: a["energy"] for a in actors},
            "deficits": deficits, "key_steps": events[:24], "steps_truncated": len(events) > 24,
            "coverage": {"full_enemy_ai": False, "game_score": False, "survival": False,
                         "ordinary_direct": True, "major_traces": False, "eidolon": 0},
            "toughness_scope": "legacy 30-per-basic units; weakness-matched capacity, not actual bar transitions or break damage",
            "buff_scope": "Herta skill +20% at supplied high-HP state; no major traces, techniques, ally-target buffs or equipment triggers"}
