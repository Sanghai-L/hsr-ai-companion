from copy import deepcopy
import pytest

from companion.calculators.timeline import calculate
from companion.calculators.resources import transact
from companion.contracts import CompanionError
from companion.experiments.service import execute
from tests.experiments.helpers import fixture


def run(value):
    return calculate(value["parameters"], value["budget"])


def test_speed_change_preserves_remaining_progress_independent_hand_result():
    result = run(fixture("timeline"))
    assert [e["at"] for e in result["events"] if e["kind"] == "basic"] == [75, 125, 175]
    assert result["energy"] == {"A": 60} and result["sp"] == 3


def test_advance_uses_full_gauge_and_delay_can_exceed_base_gauge():
    value = fixture("timeline")
    value["parameters"]["scheduled"] = [{"at": 50, "actor": "A", "kind": "advance", "value": .25}]
    assert run(value)["events"][1]["at"] == 75
    value["parameters"]["scheduled"] = [{"at": 0, "actor": "A", "kind": "delay", "value": .5}]
    assert run(value)["events"][1]["at"] == 150


def test_unaffordable_action_is_atomic_and_reports_deficit():
    value = fixture("timeline")
    action = value["parameters"]["actors"][0]["rotation"][0]
    action.update(kind="skill", sp_cost=1, energy_gain=30)
    result = run(value)
    event = result["events"][-1]
    assert event["executed"] is False and event["deficits"] == {"sp": 1}
    assert result["energy"] == {"A": 0} and result["sp"] == 0
    assert result["termination"] == "resource_deficit"


def test_ultimate_window_energy_regen_and_overflow():
    value = fixture("timeline")
    value["parameters"]["actors"][0].update(energy=80, energy_regen=.5)
    ultimate = {"kind": "ultimate", "sp_cost": 0, "sp_gain": 0, "energy_cost": 100, "energy_gain": 5, "regen_applies": False, "effects": []}
    value["parameters"]["scheduled"].append({"at": 100, "actor": "A", "kind": "ultimate", "action": ultimate})
    result = run(value)
    assert [e["at"] for e in result["events"] if e["kind"] == "basic"] == [75,125,175]
    assert result["events"][1]["overflow"]["energy"] == 10
    assert result["energy"] == {"A": 65}
    assert next(e for e in result["events"] if e["kind"] == "ultimate")["energy"] == 5


def test_ultimate_at_equal_av_is_explicitly_before_natural_turn():
    value = fixture("timeline")
    value["parameters"]["scheduled"] = [{"at": 100, "actor": "A", "kind": "ultimate", "action": {
        "kind": "ultimate", "sp_cost": 0, "sp_gain": 0, "energy_cost": 100, "energy_gain": 0, "regen_applies": False, "effects": []}}]
    result = run(value)
    assert result["termination"] == "resource_deficit" and len(result["events"]) == 1
    assert result["events"][0]["at"] == 100


def test_actor_effects_and_zero_time_loop_terminate_by_budget():
    value = fixture("timeline")
    value["parameters"]["scheduled"] = []
    value["budget"]["max_events"] = 7
    value["parameters"]["actors"][0]["rotation"][0]["effects"] = [{"kind":"advance", "target":"A", "value":1}]
    result = run(value)
    assert result["termination"] == "event_budget" and len(result["events"]) == 7
    assert all(e["at"] == 100 for e in result["events"])


def test_av_budget_never_masquerades_as_complete_requested_horizon():
    value = fixture("timeline")
    value["budget"]["max_av"] = 80
    result = execute(value).to_dict()
    assert result["status"] == "partial" and result["data"]["result"]["termination"] == "av_budget"
    assert [e["at"] for e in result["data"]["result"]["events"] if e["kind"] == "basic"] == [75]


def test_missing_speed_precision_returns_interval_instead_of_exact_order():
    value = fixture("timeline")
    value["parameters"]["actors"][0]["speed_precision"] = 1
    result = execute(value).to_dict()
    assert result["status"] == "partial" and result["missing_fields"]
    bounds = result["data"]["result"]["precision_ranges"][0]["base_av_interval_without_scheduled_effects"]
    assert bounds == [10000/101, 100]
    assert result["data"]["result"]["events"] == []


def test_invalid_actor_energy_and_effect_target_are_errors():
    value = fixture("timeline")
    value["parameters"]["actors"][0]["energy"] = 101
    with pytest.raises(CompanionError):
        run(value)
    value = fixture("timeline")
    value["parameters"]["scheduled"][0]["value"] = 0
    with pytest.raises(CompanionError):
        run(value)
    value = fixture("timeline")
    value["parameters"]["scheduled"][0]["actor"] = "missing"
    with pytest.raises(CompanionError):
        run(value)
