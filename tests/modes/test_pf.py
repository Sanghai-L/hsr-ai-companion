from companion.modes.analysis import analyze
from tests.simulation.representative_cases import case


def test_pf_target_density_and_explicit_followups_change_the_choice():
    result = analyze("pure_fiction", case("pf"))
    assert result.status == "success" and result.data["recommendation_ids"] == ["herta"]
    row = next(row for row in result.data["outcomes"] if row["candidate_id"] == "herta")
    assert row["expected_damage"] == 24300
    assert row["action_counts"]["1013:base:follow_up"] == 2
    assert result.data["mode_details"]["game_points"] is None


def test_without_crossings_no_followup_is_invented():
    value = case("pf")
    value["scenario"]["threshold_crossings"] = []
    row = analyze("pure_fiction", value).data["outcomes"][1]
    assert row["expected_damage"] == 18900 and "1013:base:follow_up" not in row["action_counts"]


def test_missing_pf_data_returns_specific_qualitative_direction():
    result = analyze("pure_fiction")
    assert result.status == "partial" and result.data["comparison"] is None
    assert any("补怪" in line for line in result.data["guidance"])
