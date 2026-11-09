import pytest

from companion.contracts import CompanionError
from companion.planning.sensitivity import analyze
from tests.simulation.representative_cases import case


def test_target_count_reverses_recommendation_with_exact_tested_conditions():
    result = analyze(case(), [{"field": "scenario.target_count", "values": [1, 2, 3]}], 10)
    assert result.status == "success" and not result.data["robust_within_tested_values"]
    assert result.data["baseline"]["recommendation_ids"] == ["dan-heng"]
    assert result.data["reversal_conditions"] == [{"field": "scenario.target_count", "value": 3, "before": ["dan-heng"], "after": ["herta"]}]
    assert result.data["confidence_interval"] is None


def test_stability_is_only_within_tested_values_and_no_cross_axis_grid():
    result = analyze(case(), [{"field": "scenario.target_count", "values": [1, 2]},
                              {"field": "scenario.phases.0.damage_taken_multiplier", "values": [.5, 1, 2]}], 10)
    assert result.data["robust_within_tested_values"] and len(result.data["scenarios"]) == 5


def test_unknown_sensitivity_fields_are_not_silently_ignored():
    with pytest.raises(CompanionError):
        analyze(case(), [{"field": "scenario.arbitrary", "values": [1, 2]}], 10)
