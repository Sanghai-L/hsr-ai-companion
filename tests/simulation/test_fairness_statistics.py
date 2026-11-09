from copy import deepcopy
import math

import pytest

from companion.contracts import CompanionError
from companion.simulation.compare import compare
from companion.simulation.rotation import prepare
from tests.simulation.representative_cases import case


def test_independent_skill_damage_and_resource_hand_calculation():
    result = compare(case())
    assert result.status == "success"
    rows = result.data["outcomes"]
    # 2 * (2000 * 2.6 * .5 defense * .9 unbroken * 1.5 expected crit) + 6 * 450
    assert rows[0]["expected_damage"] == 9720
    # Herta skill lv10 all-target 1.0, +20% high-HP damage bonus; no major trace.
    assert rows[1]["expected_damage"] == 5940
    assert [row["final_sp"] for row in rows] == [5, 5]
    assert rows[0]["final_energy"]["1002:base"] == 60
    assert rows[1]["final_energy"]["1013:base"] == 60
    assert result.data["recommendation_ids"] == ["dan-heng"]
    assert "probability" not in result.data and "confidence_interval" not in result.data


def test_swap_candidates_preserves_conditions_scores_and_recommendation():
    value = case()
    forward = compare(value).data
    value["candidates"].reverse()
    reverse = compare(value).data
    assert forward["conditions_fingerprint"] == reverse["conditions_fingerprint"]
    assert forward["recommendation_ids"] == reverse["recommendation_ids"]
    assert {r["candidate_id"]: r["expected_damage"] for r in forward["outcomes"]} == {r["candidate_id"]: r["expected_damage"] for r in reverse["outcomes"]}


def test_equal_results_report_both_winners():
    value = case()
    second = deepcopy(value["candidates"][0])
    second["id"] = "same-team"
    value["candidates"][1] = second
    assert set(compare(value).data["recommendation_ids"]) == {"dan-heng", "same-team"}


def test_different_investment_is_rejected_or_unranked_when_declared():
    value = case()
    value["candidates"][1]["investment_key"] = "different-budget"
    with pytest.raises(CompanionError) as error:
        compare(value)
    assert error.value.code == "VERSION_INCOMPATIBLE"
    value["difference_declaration"] = "明确比较不同投资，只作场景对照"
    result = compare(value)
    assert result.status == "partial" and result.data["ranking"] is None


@pytest.mark.parametrize("change", ["unknown_character", "critical_mechanism", "unknown_atk", "rounded_speed"])
def test_critical_unknowns_do_not_become_zero_contribution(change):
    value = case()
    member = value["candidates"][1]["members"][0]
    if change == "unknown_character":
        member.update(character_id="99999", form_id="99999:base")
    elif change == "critical_mechanism":
        member["required_mechanisms"] = ["unimplemented_core_mechanism"]
    elif change == "unknown_atk":
        member["atk"] = None
    else:
        member["speed_precision"] = 1
    result = compare(value)
    assert result.status == "partial" and result.data["ranking"] is None
    assert result.data["outcomes"][1]["expected_damage"] is None and result.missing_fields


def test_resource_deficit_is_atomic_and_is_not_a_victory():
    value = case()
    value["scenario"]["initial_sp"] = 0
    result = compare(value)
    for row in result.data["outcomes"]:
        assert row["status"] == "resource_deficit"
        assert row["expected_damage"] == 0 and row["final_sp"] == 0
        assert row["deficits"][0]["sp"] == 1
        assert all(energy == 0 for energy in row["final_energy"].values())
    assert result.data["ranking"] is None


def test_ultimate_uses_real_cap_cost_and_five_energy_return():
    value = case()
    value["scenario"]["initial_energy_fraction"] = .7
    for candidate in value["candidates"]:
        candidate["members"][0]["ultimate_policy"] = "after_turn_when_ready"
    row = compare(value).data["outcomes"][0]
    assert row["action_counts"]["1002:base:ultimate"] == 1
    assert row["final_energy"]["1002:base"] == 35
    assert row["expected_damage"] == 15120


@pytest.mark.parametrize("field,value", [("window_av", 201), ("initial_sp", 6)])
def test_window_and_initial_resource_bounds_are_checked(field, value):
    request = case()
    request["scenario"][field] = value
    with pytest.raises(CompanionError):
        prepare(request)


@pytest.mark.parametrize("field,value", [("data_version", "unknown"), ("game_version", "4.7")])
def test_unverified_versions_refuse_frozen_skill_ranking(field, value):
    request = case()
    request[field] = value
    with pytest.raises(CompanionError) as error:
        compare(request)
    assert error.value.code == "VERSION_INCOMPATIBLE"


def test_nonfinite_inputs_are_rejected():
    request = case()
    request["candidates"][0]["members"][0]["atk"] = math.nan
    with pytest.raises(CompanionError):
        compare(request)


@pytest.mark.parametrize("char_id", ["1312", "1221"])
def test_known_unmodelled_passive_or_capacity_is_not_silently_ignored(char_id):
    request = case()
    member = request["candidates"][0]["members"][-1]
    member.update(character_id=char_id, form_id=char_id + ":base")
    if char_id == "1221":
        request["scenario"]["initial_energy_fraction"] = .8
    result = compare(request)
    assert result.status == "partial" and result.data["outcomes"][0]["expected_damage"] is None
    assert result.missing_fields
