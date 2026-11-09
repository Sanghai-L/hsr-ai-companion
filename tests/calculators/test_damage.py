import json
from pathlib import Path
import pytest

from companion.calculators.damage import calculate
from companion.contracts import CompanionError
from companion.experiments.service import execute
from tests.experiments.helpers import fixture


def test_independent_rational_hand_fixture_and_each_zone():
    benchmark = json.loads((Path(__file__).resolve().parents[2] / "benchmarks/formulas/damage.json").read_bytes())
    result = calculate(benchmark["experiment"]["parameters"])
    assert result["value"] == pytest.approx(2025, abs=1e-10)
    assert result["zones"] == benchmark["zone_expected"]
    assert result["scope"] == "fixed_state_direct_damage"


@pytest.mark.parametrize("changes,expected", [
    ({"def_reduction": .4, "def_ignore": .1}, 2700),
    ({"def_reduction": 1, "def_ignore": 1}, 4050),
    ({"resistance": -.2}, 3037.5),
    ({"vulnerability": 0}, 1620),
    ({"crit_mode": "noncrit"}, 1350),
    ({"crit_mode": "crit"}, 2700),
    ({"crit_rate": 2}, 2700),
    ({"crit_rate": -1}, 1350),
    ({"multiplier": 0}, 0),
    ({"broken": True}, 2250),
])
def test_defense_resistance_vulnerability_crit_zero_and_boundary(changes, expected):
    parameters = fixture("damage")["parameters"]
    parameters.update(changes)
    assert calculate(parameters)["value"] == pytest.approx(expected, rel=1e-12)


def test_single_factor_disabled_gain_zero_base_and_units():
    parameters = fixture("damage")["parameters"]
    parameters.update(crit_mode="noncrit", change={"field": "crit_damage", "value": 2})
    assert calculate(parameters)["single_factor"]["relative_delta"] == 0
    parameters.update(multiplier=0)
    assert calculate(parameters)["single_factor"]["relative_delta"] is None
    parameters["stat"]["unit"] = "percent"
    with pytest.raises(CompanionError):
        calculate(parameters)


def test_unknown_imprecise_panel_reapplication_and_extreme_resistance_do_not_guess():
    for update, code in [({"value": None}, "MISSING_DATA"), ({"precision": 1}, "MISSING_DATA"), ({"equipment_bonus": 1}, "INVALID_INPUT")]:
        value = fixture("damage")["parameters"]
        value["stat"].update(update)
        with pytest.raises(CompanionError) as exc:
            calculate(value)
        assert exc.value.code == code
    value = fixture("damage")["parameters"]
    value["res_penetration"] = 3
    with pytest.raises(CompanionError) as exc:
        calculate(value)
    assert exc.value.code == "UNSUPPORTED"


@pytest.mark.parametrize("kind", ["dot", "break", "super_break", "true", "elation"])
def test_other_damage_types_return_coverage_failure(kind):
    value = fixture("damage")["parameters"]
    value["damage_type"] = kind
    with pytest.raises(CompanionError) as exc:
        calculate(value)
    assert exc.value.code == "UNSUPPORTED"


def test_envelope_validates_and_preserves_exact_inputs_and_assumptions():
    value = fixture("damage")
    result = execute(value).to_dict()
    assert result["status"] == "success" and result["data"]["input"] == value
    assert result["assumptions"] == value["assumptions"] and result["warnings"]
