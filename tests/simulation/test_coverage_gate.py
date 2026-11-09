from copy import deepcopy
import json
from pathlib import Path

import pytest

from companion.contracts import CompanionError, ErrorCode
from companion.simulation.preflight import CoverageRegistry, preflight

ROOT = Path(__file__).resolve().parents[2]


def fixture():
    return json.loads((ROOT / "tests/fixtures/requests/simulation.json").read_bytes())["experiment"]


def test_every_enemy_phase_is_checked_and_high_precision_refused():
    value = fixture()
    value["parameters"]["precision"] = "high"
    result = preflight(value)
    assert result.status == "error" and result.error["code"] == "UNSUPPORTED"
    assert all(f"enemy:{eid}:phase" in result.error["details"]["mechanisms"] for eid in ("3013010", "1023020", "3024020"))
    assert not result.data["game_accuracy_certified"] and not result.data["game_ranking_allowed"]


def test_deleting_a_required_equipment_trigger_rejects_instead_of_silently_zeroing():
    value = fixture()
    value["parameters"]["build"]["members"][0]["light_cone"] = {"entity_id": "20002", "instance_id": "test-cone-1",
        "level": 80, "promotion": 6, "superimposition": 1, "path": "Warrior", "source_ref": "synthetic:test"}
    registry = CoverageRegistry()
    registry.entries["light_cone:20002:s1"] = {"key": "light_cone:20002:s1", "status": "approximate", "reason": "synthetic verified trigger path",
        "impact": "synthetic impact", "validation_cases": ["tests/simulation/test_coverage_gate.py"], "model_executable": True, "critical": True}
    assert preflight(value, coverage=registry).data["can_execute_model_diagnostic"]
    del registry.entries["light_cone:20002:s1"]
    result = preflight(value, coverage=registry)
    assert result.status == "partial" and not result.data["can_execute_model_diagnostic"]
    missing = next(c for c in result.data["checks"] if c["key"] == "light_cone:20002:s1")
    assert missing["status"] == "unknown"
    assert not result.data["complete_supported"]


def test_approximation_warnings_remain_in_serialized_tool_result():
    result = preflight(fixture()).to_dict()
    assert result["status"] == "partial"
    assert result["data"]["can_execute_model_diagnostic"] and not result["data"]["game_ranking_allowed"]
    assert any("受击回能" in text for text in result["warnings"])
    assert result["data"]["coverage_fingerprint"]


def test_higher_eidolons_all_active_lower_ranks_and_relic_triggers_are_required():
    value = fixture()
    value["parameters"]["build"]["members"][0]["eidolon"] = 2
    required = CoverageRegistry().required(value)
    assert all(f"eidolon:1408:{rank}" in required for rank in range(3))
    assert not preflight(value).data["can_execute_model_diagnostic"]


def test_unknown_character_does_not_inherit_inactive_turbulence():
    value = fixture()
    member = value["parameters"]["build"]["members"][0]
    member.update(character_id="unknown", form_id="unknown:base")
    result = preflight(value)
    assert "scenario:alpha-moc:turbulence:active" in result.data["required_mechanisms"]
    assert not result.data["can_execute_model_diagnostic"]


def test_no_false_precision_by_switching_to_expected_crit_or_relabeling_version():
    value = fixture()
    value["parameters"]["mode"] = "expected"
    result = preflight(value)
    assert not result.data["game_ranking_allowed"] and any("不预测击杀" in w for w in result.warnings)


def test_duplicate_gear_instance_is_rejected_before_coverage():
    value = fixture()
    cone = {"entity_id": "test", "instance_id": "same-instance", "level": 80, "promotion": 6,
            "superimposition": 1, "path": "Shaman", "source_ref": "synthetic:test"}
    for member in value["parameters"]["build"]["members"][1:3]:
        member["light_cone"] = deepcopy(cone)
    with pytest.raises(CompanionError) as caught:
        preflight(value)
    assert caught.value.code == ErrorCode.CONFLICT


def test_missing_state_is_never_defaulted_and_unknown_dsl_field_is_rejected():
    value = fixture()
    del value["parameters"]["initial_resources"]["energy_ratio"]
    with pytest.raises(CompanionError) as caught:
        preflight(value)
    assert caught.value.code == ErrorCode.MISSING_DATA
    value = fixture()
    value["parameters"]["build"]["members"][0]["hooks"] = []
    with pytest.raises(CompanionError) as caught:
        preflight(value)
    assert caught.value.code == ErrorCode.INVALID_INPUT
