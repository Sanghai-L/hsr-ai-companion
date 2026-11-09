"""Select a sourced MoC candidate without conferring simulation coverage.

An instance ID remains the instance ID even when its display name comes from a
parent template. Empty schedule/region/build fields remain unknown.
"""
from copy import deepcopy
import hashlib
import re
import unicodedata

from companion.contracts import CompanionError, ErrorCode, canonical

ROMAN_FLOORS = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6,
                "VII": 7, "VIII": 8, "IX": 9, "X": 10, "XI": 11, "XII": 12}


def floor_number(row):
    match = re.search(r"\(([IVX]+)\)$", row.get("name", ""))
    return ROMAN_FLOORS.get(match[1]) if match else None


def enemy_identity(instance_id, names):
    if not isinstance(names, dict) or any(not isinstance(item, dict) for item in names.values()):
        raise CompanionError(ErrorCode.VERSION_INCOMPATIBLE, "敌人身份来源格式变化")
    entity_id = str(instance_id)
    if entity_id in names:
        value = names[entity_id]
        parent = entity_id
    else:
        matches = [(key, value) for key, value in names.items() if any(str(child) == entity_id for child in value.get("child", []))]
        if len(matches) != 1:
            raise CompanionError(ErrorCode.MISSING_DATA, "敌人变体身份缺失或不唯一", details={"fields": ["enemy:" + entity_id]})
        parent, value = matches[0]
    label = value.get("zh") or value.get("en")
    if not label:
        raise CompanionError(ErrorCode.MISSING_DATA, "敌人名称缺失", details={"fields": ["enemy:" + entity_id + ".name"]})
    return {"instance_id": entity_id, "name_template_id": parent, "name": label,
            "name_from_parent": parent != entity_id}


def select_floor(rows, names, *, floor, period_id, game_version, source_refs, source_hashes, region=None):
    if type(floor) is not int or floor not in ROMAN_FLOORS.values():
        raise CompanionError(ErrorCode.INVALID_INPUT, "混沌楼层应为1～12")
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise CompanionError(ErrorCode.VERSION_INCOMPATIBLE, "关卡来源格式变化")
    selected = [row for row in rows if floor_number(row) == floor]
    if len(selected) != 1:
        raise CompanionError(ErrorCode.MISSING_DATA, "来源无法唯一定位所选层数", details={"fields": ["floor"]})
    row = selected[0]
    required = {"desc", "param", "countdown", "event_id_list1", "event_id_list2"}
    missing = required - set(row)
    if missing:
        raise CompanionError(ErrorCode.MISSING_DATA, "所选关卡缺少必要字段", details={"fields": sorted(missing)})
    if not isinstance(source_refs, list) or not source_refs or not source_hashes:
        raise CompanionError(ErrorCode.MISSING_DATA, "场景来源与内容哈希不可省略")
    if type(row["countdown"]) is not int or not 1 <= row["countdown"] <= 1000 or not isinstance(row["param"], list):
        raise CompanionError(ErrorCode.VERSION_INCOMPATIBLE, "关卡轮次或效果参数格式变化")
    result = {"period_id": str(period_id), "game_version": game_version, "floor": floor, "region": region,
              "period_begin": row.get("begin_time") or None, "period_end": row.get("end_time") or None,
              "effect": {"description_raw": row["desc"], "parameters": deepcopy(row["param"])},
              "total_cycle_budget": row["countdown"], "source_refs": list(source_refs), "source_hashes": deepcopy(source_hashes),
              "sides": {}, "complete_supported": False, "game_accuracy_certified": False,
              "source_alignment_only": True}
    all_actor_ids = set()
    for side, key in (("upper", "event_id_list1"), ("lower", "event_id_list2")):
        branches = row[key]
        if not isinstance(branches, list) or len(branches) != 1:
            raise CompanionError(ErrorCode.UNSUPPORTED, "所选半层有多条编成分支，需要明确分支后才能冻结")
        stage = branches[0]
        if not isinstance(stage, dict):
            raise CompanionError(ErrorCode.VERSION_INCOMPATIBLE, "半层分支格式变化")
        required = {"stage_id", "level", "hard_level_group", "elite_group", "monster_list"}
        if required - set(stage):
            raise CompanionError(ErrorCode.MISSING_DATA, "半层缺少敌人、等级或系数字段", details={"fields": sorted(required - set(stage))})
        if (any(type(stage[key]) is not int or stage[key] <= 0 for key in ("stage_id", "level", "hard_level_group", "elite_group"))
                or stage["level"] > 120):
            raise CompanionError(ErrorCode.VERSION_INCOMPATIBLE, "敌人等级／分组必须为明确的合法整数")
        if not isinstance(stage["monster_list"], list) or not stage["monster_list"]:
            raise CompanionError(ErrorCode.MISSING_DATA, "半层缺少明确波次")
        waves = []
        for index, raw_wave in enumerate(stage["monster_list"]):
            if not isinstance(raw_wave, dict) or not raw_wave:
                raise CompanionError(ErrorCode.MISSING_DATA, "波次编成为空或格式变化")
            if any(not re.fullmatch(r"monster\d+", key) for key in raw_wave):
                raise CompanionError(ErrorCode.VERSION_INCOMPATIBLE, "波次槽位结构变化")
            members = []
            for slot, instance_id in sorted(raw_wave.items(), key=lambda item: int(item[0][7:])):
                if type(instance_id) is not int or instance_id <= 0:
                    raise CompanionError(ErrorCode.INVALID_INPUT, "敌人实例ID无效")
                identity = enemy_identity(instance_id, names)
                actor_id = f"{side}_w{index}_{slot}_{instance_id}"
                assert actor_id not in all_actor_ids
                all_actor_ids.add(actor_id)
                members.append({"actor_id": actor_id, **identity})
            waves.append({"wave_index": index, "enemies": members})
        result["sides"][side] = {"stage_id": str(stage["stage_id"]), "enemy_level": stage["level"],
                                  "hard_level_group": stage["hard_level_group"], "elite_group": stage["elite_group"],
                                  "waves": waves, "boss_phase_count": None,
                                  "ai_coverage": "unknown", "phase_coverage": "unknown", "effect_coverage": "unknown"}
    result["candidate_fingerprint"] = hashlib.sha256(canonical(result)).hexdigest()
    return result


def name_key(value):
    return "".join(unicodedata.normalize("NFKC", value).casefold().split()).replace("•", "·")


def resolve_character(name, characters, *, aliases=None):
    # No substring match: 银狼LV.999 / 银狼 and 火花 / 花火 are distinct.
    if not isinstance(name, str) or not name.strip() or len(name) > 100:
        raise CompanionError(ErrorCode.INVALID_INPUT, "角色名为空或超限")
    aliases = {name_key(key): value for key, value in (aliases or {}).items()}
    requested = aliases.get(name_key(name), name)
    matches = [(key, value) for key, value in characters.items() if name_key(value.get("name", "")) == name_key(requested)]
    if len(matches) != 1:
        raise CompanionError(ErrorCode.MISSING_DATA, "角色名无法唯一匹配实体", details={"fields": ["character:" + name]})
    entity_id, value = matches[0]
    return {"requested_name": name, "character_id": entity_id, "name": value["name"], "path": value.get("path"),
            "level": None, "eidolon": None, "equipment": None, "ownership": "unknown", "build_ready": False}
