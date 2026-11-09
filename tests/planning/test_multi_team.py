from copy import deepcopy
from itertools import product

import pytest

from companion.contracts import CompanionError
from companion.planning.multi_team import conflicts, plan
from tests.simulation.representative_cases import multi_case


@pytest.mark.parametrize("mode", ["memory_of_chaos", "anomaly_arbitration"])
def test_small_enumeration_matches_independent_pairwise_resource_check(mode):
    request = multi_case(mode)
    actual = plan(request)
    slots = request["slots"]
    independently_legal = []
    for choices in product(*(slot["request"]["candidates"] for slot in slots)):
        chars, equipment, legal = set(), set(), True
        for team in choices:
            current_chars = {m["character_id"] for m in team["members"]}
            current_equipment = {e for m in team["members"] for e in m["equipment_instances"]}
            if chars & current_chars or equipment & current_equipment:
                legal = False
            chars |= current_chars
            equipment |= current_equipment
        if legal:
            independently_legal.append(choices)
    assert actual.status == "success"
    assert actual.data["feasible_combinations"] == len(independently_legal) > 0
    for recommendation in actual.data["recommendations"]:
        occupied = set()
        for assignment in recommendation["assignments"]:
            chars = {form.split(":")[0] for form in assignment["members"]}
            assert not occupied & chars
            occupied |= chars


def test_same_character_different_forms_and_equipment_instance_conflict():
    request = multi_case()
    first = request["slots"][0]["request"]["candidates"][0]
    second = deepcopy(first)
    second["members"][0]["form_id"] = second["members"][0]["character_id"] + ":other-form"
    clashes = conflicts(request["slots"], [first, second], request["mode"])
    assert any(c["resource"] == "1002" for c in clashes)
    second = request["slots"][1]["request"]["candidates"][0]
    first["members"][0]["equipment_instances"] = ["cone-instance"]
    second["members"][0]["equipment_instances"] = ["cone-instance"]
    assert any(c["kind"] == "equipment" for c in conflicts(request["slots"], [first, second], request["mode"]))


def test_king_may_reuse_knight_characters_and_equipment():
    request = multi_case("anomaly_arbitration")
    king = deepcopy(request["slots"][0])
    king.update(id="king", stage_type="king")
    request["slots"].append(king)
    result = plan(request)
    assert result.status == "success" and result.data["feasible_combinations"] > 0
    assert result.data["rules"]["king_can_reuse_knight_resources"]


def test_no_feasible_solution_returns_conflicts_and_no_illegal_plan():
    request = multi_case()
    request["slots"][1]["request"]["candidates"] = deepcopy(request["slots"][0]["request"]["candidates"])
    for slot in request["slots"]:
        for candidate in slot["request"]["candidates"]:
            candidate["members"][-1].update(character_id="1109", form_id="1109:base")
    result = plan(request)
    assert result.status == "partial" and result.data["no_solution"]
    assert result.data["recommendations"] == [] and result.data["conflicting_resources"]


def test_roster_outside_explicit_hypothesis_is_not_assumed_owned():
    request = multi_case()
    request["roster"]["available_character_ids"].remove("1002")
    with pytest.raises(CompanionError) as error:
        plan(request)
    assert error.value.code == "MISSING_DATA"


def test_bounded_search_does_not_claim_no_solution_or_optimality():
    request = multi_case()
    request["max_combinations"] = 1
    result = plan(request)
    assert result.status == "partial" and not result.data["search_complete"]
    assert not result.data["no_solution"] and result.data["recommendations"] == []
