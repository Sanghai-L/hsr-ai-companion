from copy import deepcopy
import json
from pathlib import Path

import pytest

from companion.contracts import CompanionError, ErrorCode
from companion.modes.memory_of_chaos import FrozenMoc, enemy_stats, outcome
from tests.simulation.test_backend_adapter import installed_backend
from tests.simulation.test_coverage_gate import fixture

ROOT = Path(__file__).resolve().parents[2]


def scenario():
    return FrozenMoc(ROOT / ".local/benchmarks/seed-scenario/scenario.json", ROOT / ".local/data-snapshot")


def numeric_case():
    template = {"HPBase": 10, "AttackBase": 5, "DefenceBase": 3, "SpeedBase": 100, "StanceBase": 30, "StatusResistanceBase": .1, "SpeedModifyValue": 3}
    instance = {"HPModifyRatio": 1.5, "AttackModifyRatio": 1, "DefenceModifyRatio": 1, "SpeedModifyRatio": 1, "StanceModifyRatio": 1,
                "SpeedModifyValue": 2, "DamageTypeResistance": [{"DamageType": "Physical", "Value": {"Value": .2}}]}
    hard = {"HPRatio": 2, "AttackRatio": 3, "DefenceRatio": 4, "SpeedRatio": 1.1, "StanceRatio": 1}
    elite = {"HPRatio": 5, "AttackRatio": 2, "DefenceRatio": 1, "SpeedRatio": 1, "StanceRatio": 1}
    return instance, template, hard, elite


def test_source_stat_conversion_matches_independent_hand_arithmetic():
    actual = enemy_stats(*numeric_case(), level=60)
    assert actual["hp"] == 150  # 10 × 2 × 5 × 1.5
    assert actual["atk"] == 30 and actual["def_"] == 12
    assert actual["spd"] == 115 and actual["max_toughness"] == 30
    assert actual["effect_res"] == .14
    assert actual["resistance"]["physical"] == .2 and actual["resistance"]["fire"] == 0


def test_missing_resistance_or_numeric_multiplier_never_becomes_default_one_or_zero():
    instance, template, hard, elite = numeric_case()
    del instance["DamageTypeResistance"]
    with pytest.raises(CompanionError) as caught:
        enemy_stats(instance, template, hard, elite, level=60)
    assert caught.value.code == ErrorCode.MISSING_DATA
    instance, template, hard, elite = numeric_case()
    del elite["HPRatio"]
    with pytest.raises(CompanionError) as caught:
        enemy_stats(instance, template, hard, elite, level=60)
    assert caught.value.code == ErrorCode.MISSING_DATA


def test_frozen_scenario_stat_groups_override_instance_defaults_and_missing_ai_is_visible():
    audit = scenario().inspect()
    assert not audit["complete_supported"] and not audit["game_accuracy_certified"]
    assert all(row["instance_groups"] == {"hard": 1, "elite": 1} for row in audit["enemy_audit"])
    assert all(row["used_stage_groups"] == {"hard": 3, "elite": 164} for row in audit["enemy_audit"])
    assert all(row["ai_path_reference"] and not row["ai_behavior_file_present"] for row in audit["enemy_audit"])
    assert not audit["full_stage_stars_available"]


def test_modified_scenario_is_rejected(tmp_path):
    raw = json.loads((ROOT / ".local/benchmarks/seed-scenario/scenario.json").read_bytes())
    raw["enemy_level"] = 1
    changed = tmp_path / "scenario.json"
    changed.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(CompanionError) as caught:
        FrozenMoc(changed, ROOT / ".local/data-snapshot")
    assert caught.value.code == ErrorCode.VERSION_INCOMPATIBLE


def test_complete_stage_refuses_placeholder_ai_even_if_caller_requests_high_precision():
    value = fixture()
    with pytest.raises(CompanionError) as caught:
        scenario().backend_input(value)
    assert caught.value.code == ErrorCode.UNSUPPORTED
    assert any("萨姆" in text for text in caught.value.details["blockers"])


def test_corrected_stats_and_resistances_reach_actual_compiled_enemies():
    value = fixture()
    mode = scenario()
    input_value = mode.backend_input(value, model_diagnostic=True)
    actual = installed_backend().compile(input_value)
    expected = mode.inspect()["enemy_overrides"]
    for enemy in actual["compiled_enemies"]:
        for key, number in expected[enemy["actor_id"]].items():
            assert enemy[key] == number
        assert enemy["level"] == 95
    assert len(actual["compiled_enemies"]) == 3
    assert "INCOMPLETE-MODEL" in input_value.stage["stage"]["stage_id"]


@pytest.mark.parametrize("reason,expected", [("target_killed", "victory"), ("all_allies_dead", "defeat"),
    ("max_action_value_reached", "timeout"), ("max_cycles", "timeout"), ("unknown", "incomplete")])
def test_wipe_and_timeout_are_never_victory(reason, expected):
    value = outcome(reason)
    assert value["outcome"] == expected and value["victory"] == (expected == "victory")
    assert not outcome(reason, truncated=True)["victory"]
