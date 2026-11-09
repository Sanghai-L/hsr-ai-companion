from companion.modes.analysis import analyze
from tests.simulation.representative_cases import case


def test_as_separates_pre_and_post_break_and_discloses_toughness_scope():
    result = analyze("apocalyptic_shadow", case("as"))
    assert result.status == "success"
    row = result.data["outcomes"][0]
    # (3510 + 1350)*.5 unbroken + (3900 + 1500)*2 broken
    assert row["expected_damage"] == 13230
    assert row["toughness_capacity_by_element"]["wind"] == 60
    assert row["final_energy"]["1002:base"] == 60 and result.data["mode_details"]["game_score"] is None


def test_missing_break_window_does_not_generate_overall_recommendation():
    request = case("as")
    request["scenario"]["phases"] = [request["scenario"]["phases"][0] | {"until_av": 200}]
    result = analyze("apocalyptic_shadow", request)
    assert result.status == "partial" and result.data["ranking"] is None
    assert "scenario.unbroken_and_broken_windows" in result.missing_fields
