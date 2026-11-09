from copy import deepcopy

import pytest

from companion.contracts import CompanionError, ErrorCode
from companion.modes.scenario_candidate import enemy_identity, resolve_character, select_floor


def inputs():
    stage = {"stage_id": 123, "level": 92, "hard_level_group": 3, "elite_group": 2,
             "monster_list": [{"monster0": 11, "monster1": 11}, {"monster0": 101}]}
    rows = [{}, {"name": "原创合成关卡 (XI)", "desc": "合成效果，不是游戏数据", "param": [5, 20], "countdown": 30,
                 "begin_time": "", "end_time": "", "event_id_list1": [deepcopy(stage)], "event_id_list2": [deepcopy(stage)]}]
    names = {"11": {"zh": "测试假人", "en": "Synthetic Dummy", "child": [11, 101]}}
    return rows, names


def select(rows, names):
    return select_floor(rows, names, floor=11, period_id="synthetic", game_version="synthetic",
                        source_refs=["synthetic:original-case"], source_hashes={"fixture": "a" * 64})


def test_same_type_duplicates_keep_separate_actor_ids_and_variant_id_is_not_collapsed():
    value = select(*inputs())
    all_actors = [m["actor_id"] for side in value["sides"].values() for wave in side["waves"] for m in wave["enemies"]]
    assert len(all_actors) == 6 and len(set(all_actors)) == 6
    variant = value["sides"]["lower"]["waves"][1]["enemies"][0]
    assert variant["instance_id"] == "101" and variant["name_template_id"] == "11"
    assert variant["name_from_parent"]


def test_unknown_dates_region_phases_and_simulation_coverage_stay_unknown():
    value = select(*inputs())
    assert value["period_begin"] is None and value["period_end"] is None and value["region"] is None
    assert value["sides"]["upper"]["boss_phase_count"] is None
    assert value["sides"]["upper"]["effect_coverage"] == "unknown"
    assert value["source_alignment_only"] and not value["complete_supported"] and not value["game_accuracy_certified"]


def test_ambiguous_parent_name_does_not_guess_instance_template():
    _, names = inputs()
    names["12"] = {"zh": "另一个测试假人", "child": [101]}
    with pytest.raises(CompanionError) as caught:
        enemy_identity("101", names)
    assert caught.value.code == ErrorCode.MISSING_DATA


def test_empty_unknown_wave_and_duplicate_floor_are_rejected():
    rows, names = inputs()
    rows[1]["event_id_list1"][0]["monster_list"] = [{}]
    with pytest.raises(CompanionError):
        select(rows, names)
    rows, names = inputs()
    rows.append(deepcopy(rows[1]))
    with pytest.raises(CompanionError) as caught:
        select(rows, names)
    assert caught.value.code == ErrorCode.MISSING_DATA


def test_multiple_stage_branches_are_not_silently_flattened_into_one_encounter():
    rows, names = inputs()
    rows[1]["event_id_list1"].append(deepcopy(rows[1]["event_id_list1"][0]))
    with pytest.raises(CompanionError) as caught:
        select(rows, names)
    assert caught.value.code == ErrorCode.UNSUPPORTED


def test_boolean_or_unknown_enemy_level_never_becomes_a_numeric_default():
    rows, names = inputs()
    rows[1]["event_id_list1"][0]["level"] = True
    with pytest.raises(CompanionError) as caught:
        select(rows, names)
    assert caught.value.code == ErrorCode.VERSION_INCOMPATIBLE


def test_same_character_different_entity_names_never_use_substring_fallback():
    catalog = {"1006": {"name": "银狼", "path": "Warlock"}, "1506": {"name": "银狼LV.999", "path": "Elation"},
               "1306": {"name": "花火", "path": "Shaman"}, "1501": {"name": "火花", "path": "Elation"}}
    assert resolve_character("银狼LV.999", catalog)["character_id"] == "1506"
    assert resolve_character("银狼", catalog)["character_id"] == "1006"
    assert resolve_character("火花", catalog)["character_id"] == "1501"
    assert resolve_character("花火", catalog)["character_id"] == "1306"
    assert resolve_character("银狼lv.999", catalog)["character_id"] == "1506"
    assert resolve_character("银狼lv.999", catalog)["eidolon"] is None
    with pytest.raises(CompanionError):
        resolve_character("银狼LV", catalog)


def test_name_alias_requires_explicit_mapping_and_never_sets_build_defaults():
    catalog = {"1412": {"name": "刻律德菈", "path": "Shaman"}}
    value = resolve_character("刻律德拉", catalog, aliases={"刻律德拉": "刻律德菈"})
    assert value["character_id"] == "1412" and value["ownership"] == "unknown"
    assert value["level"] is None and value["equipment"] is None and not value["build_ready"]
