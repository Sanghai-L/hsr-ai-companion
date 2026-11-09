from copy import deepcopy
import json
from pathlib import Path

import pytest

from companion.contracts import CompanionError, ErrorCode, canonical
from companion.simulation.builds import import_snapshot, speed_range, to_backend_build, validate_build
from tests.simulation.test_backend_adapter import installed_backend, legacy_input
from tests.simulation.test_coverage_gate import fixture

ROOT = Path(__file__).resolve().parents[2]


def build():
    return fixture()["parameters"]["build"]


def snapshot():
    members = build()["members"]
    return {"account_id": "test-account", "snapshot_id": "test-snapshot", "observed_at": "2026-11-08T00:00:00Z",
            "versions": {"game": "4.4"}, "roster_completeness": "partial",
            "characters": [{"character_id": m["character_id"], "form_id": m["form_id"], "ownership": "owned"} for m in members],
            "equipment": [], "fields": []}


def full_overrides():
    return {m["form_id"]: {k: deepcopy(v) for k, v in m.items() if k not in {"character_id", "form_id", "ownership"}} for m in build()["members"]}


def field(stat, value, *, unit="flat", precision=None, basis="public_panel"):
    return {"entity_id": "character:1408:base", "field_id": stat,
            "quantity": {"value": value, "unit": unit, "state": "known" if value is not None else "unknown", "precision": precision},
            "source": {"type": "manual", "ref": "synthetic:panel", "observed_at": "2026-11-08T00:00:00Z"}, "confirmed": True, "basis": basis}


def test_public_showcase_does_not_guess_equipment_or_graduated_build():
    original = snapshot()
    result = import_snapshot(original, [m["form_id"] for m in build()["members"]])
    assert result["build"] is None
    assert "members.0.light_cone" in result["missing_fields"] and "members.0.relics" in result["missing_fields"]
    assert "light_cone" not in result["draft"]["members"][0]
    assert len(result["questions"]) == 4
    assert all(q["fields"] for q in result["questions"])


def test_complete_manual_supplement_is_independent_and_no_snapshot_mutation():
    original = snapshot()
    before = canonical(original)
    result = import_snapshot(original, [m["form_id"] for m in build()["members"]], overrides=full_overrides())
    assert not result["missing_fields"] and result["validation"]["executable"]
    assert not result["account_modified"] and canonical(original) == before
    assert result["build"]["snapshot_id"] == original["snapshot_id"]


def test_hypothetical_future_ownership_does_not_change_account_facts():
    original = snapshot()
    original["characters"][0]["ownership"] = "not_owned"
    before = canonical(original)
    forms = [m["form_id"] for m in build()["members"]]
    real = import_snapshot(original, forms, overrides=full_overrides())
    assert "members.0.ownership" in real["missing_fields"]
    hypothetical = import_snapshot(original, forms, overrides=full_overrides(), hypothesis=True, assumptions=["如果未来抽到该角色，按独立E0构筑分析"])
    assert hypothetical["build"]["origin"] == "hypothesis" and hypothetical["validation"]["executable"]
    assert hypothetical["build"]["members"][0]["ownership"] == "not_owned"
    assert canonical(original) == before


def test_public_panel_is_audit_only_and_never_double_adds_equipment():
    value = build()
    value["members"][0]["attributes"]["atk"] = {"value": 2800, "precision": 0, "basis": "public_panel", "source_ref": "synthetic:panel"}
    report = validate_build(value)
    converted = to_backend_build(value, fixture()["parameters"]["policy"])
    assert report["attribute_audit"][0]["usage"] == "validation_only"
    assert all("base_stats" not in m for m in converted["build"]["team"])
    assert any("不作为基础属性再次叠加装备" in w for w in report["limitations"])


def test_base_attribute_override_is_not_silently_ignored():
    value = build()
    value["members"][0]["attributes"]["atk"] = {"value": 800, "precision": 0, "basis": "base", "source_ref": "synthetic:base"}
    assert not validate_build(value)["executable"]
    with pytest.raises(CompanionError) as caught:
        to_backend_build(value, fixture()["parameters"]["policy"])
    assert caught.value.code == ErrorCode.UNSUPPORTED


def test_speed_unknown_resolution_gives_unknown_bounds_and_known_resolution_gives_conservative_range():
    unknown = speed_range({"value": 134, "precision": None})
    assert unknown["lower"] is None and unknown["upper"] is None and not unknown["exact"]
    bounded = speed_range({"value": 134, "precision": 1})
    assert bounded["lower"] == 133 and bounded["upper"] == 135 and not bounded["exact"]
    assert speed_range({"value": 134.4, "precision": 0})["exact"]
    value = build()
    value["members"][0]["attributes"]["spd"] = {"value": 134, "precision": None, "basis": "public_panel", "source_ref": "synthetic:speed"}
    report = validate_build(value)
    assert not report["executable"] and report["speed_ranges"]["1408:base"]["lower"] is None


def test_character_light_cone_path_mismatch_and_equipment_instance_conflict():
    value = build()
    cone = {"entity_id": "23000", "instance_id": "shared", "level": 80, "promotion": 6, "superimposition": 1, "path": "Mage", "source_ref": "synthetic:test"}
    value["members"][0]["light_cone"] = cone
    with pytest.raises(CompanionError) as caught:
        validate_build(value)
    assert caught.value.code == ErrorCode.INVALID_INPUT
    value["members"][0]["light_cone"]["path"] = "Warrior"
    value["members"][1]["light_cone"] = {**cone, "path": "Shaman"}
    with pytest.raises(CompanionError) as caught:
        validate_build(value)
    assert caught.value.code == ErrorCode.CONFLICT


def test_lower_level_and_partial_traces_do_not_become_max_builds():
    value = build()
    value["members"][0].update(level=70, promotion=5, trace_policy="partial")
    report = validate_build(value)
    assert not report["executable"] and "members.0.level_scaling" in report["unsupported_fields"]
    assert value["members"][0]["level"] == 70


def test_missing_speed_and_percentage_units_are_preserved_from_snapshot():
    original = snapshot()
    original["fields"] = [field("crit_rate", 62.5, unit="percent", precision=.1), field("spd", 134, unit="speed")]
    supplements = full_overrides()
    del supplements["1408:base"]["attributes"]
    result = import_snapshot(original, [m["form_id"] for m in build()["members"]], overrides=supplements)
    assert result["build"]["members"][0]["attributes"]["crit_rate"]["value"] == .625
    assert result["validation"]["speed_ranges"]["1408:base"]["upper"] is None
    assert not result["validation"]["executable"]


def test_unknown_form_does_not_fall_back_to_character_default():
    value = build()
    value["members"][0]["form_id"] = "1408:unverified-enhancement"
    assert not validate_build(value)["executable"]


def test_exact_relic_substats_are_encoded_as_values_not_fabricated_rolls():
    value = build()
    value["members"][0]["relics"] = [{"entity_id": "test-relic", "instance_id": "test-r1", "set_id": "101",
        "slot": "feet", "level": 15, "rarity": 5, "main_stat": "spd", "main_value": 25.032, "sub_values": {"crit_rate": .0972}, "source_ref": "synthetic:relic"}]
    relic = to_backend_build(value, fixture()["parameters"]["policy"])["build"]["team"][0]["relics"]["feet"]
    assert relic["sub_values"] == {"crit_rate": .0972}
    assert relic["subs"] == {"crit_rate": 0} and relic["main_value"] == 25.032


def test_bound_constructed_team_matches_legacy_full_event_trace():
    value = fixture()
    converted = to_backend_build(value["parameters"]["build"], value["parameters"]["policy"])
    from companion.sim_backends.base import BackendInput
    legacy = legacy_input("team-a")
    original = installed_backend().execute(legacy)
    actual = installed_backend().execute(BackendInput(build=converted, stage=legacy.stage))
    assert actual["snapshot"] == original["snapshot"] and actual["events"] == original["events"]
