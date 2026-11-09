from companion.modes.analysis import analyze, select_mode
from tests.simulation.representative_cases import case


def test_aa_distinguishes_knight_projection_and_king_resource_rules():
    result = analyze("anomaly_arbitration", case("aa"))
    assert result.status == "success" and result.data["ranking"] == ["herta", "dan-heng"]
    details = result.data["mode_details"]
    assert details["roster_rules"]["knight_slots"] == 3 and details["roster_rules"]["king_can_reuse_knight_resources"]
    assert details["qualitative"] and details["quantitative"]


def test_mode_ambiguity_does_not_pick_a_silent_default():
    assert select_mode("虚构叙事和末日幻影怎么选队").status == "partial"
    assert select_mode("看看异相仲裁配队").data["selected_mode"] == "anomaly_arbitration"
