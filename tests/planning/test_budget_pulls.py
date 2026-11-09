from copy import deepcopy
import pytest

from companion.contracts import CompanionError
from companion.planning.budget import available, validate_income
from companion.planning.pulls import calculate
from companion.experiments.service import execute
from tests.experiments.helpers import fixture


def run(value):
    return calculate(value["parameters"], value["budget"])


def test_hand_computed_three_incomes_and_sequential_shared_budget():
    result = run(fixture("pull-plan"))
    single, double, skip = result["options"]
    scenarios = ("conservative","neutral","optimistic")
    assert [single["scenarios"][s]["all_targets_probability"] for s in scenarios] == [.5,1,1]
    assert [double["scenarios"][s]["all_targets_probability"] for s in scenarios] == [0,.25,.75]
    assert double["scenarios"]["neutral"]["expected_spend_conditional_on_all_targets"] == 2
    assert [skip["scenarios"][s]["remaining_resources"]["total_pulls"] for s in scenarios] == [1,2,3]
    assert result["ranking"] is None and result["options_are_alternatives"]
    assert all(o["reversal_conditions"] and o["benefit"]["account_gain_percent"] is None for o in result["options"])


def test_income_never_counted_twice_across_stages_or_before_availability():
    parameters = fixture("pull-plan")["parameters"]
    early = available(parameters, "neutral", "2026-11-08")
    late = available(parameters, "neutral", "2026-11-09")
    assert early["total_pulls"] == 1 and late["total_pulls"] == 2
    assert late["included_income_ids"] == ["single-original-event"]
    value = fixture("pull-plan")
    value["parameters"]["income"].append(deepcopy(value["parameters"]["income"][0]))
    with pytest.raises(CompanionError, match="重复"):
        run(value)
    value["parameters"]["income"][1]["id"] = "same-reward-different-label"
    with pytest.raises(CompanionError, match="重复"):
        run(value)


def test_zero_budget_reserve_jade_remainder_and_negative_inputs():
    value = fixture("pull-plan")
    value["parameters"].update(budget={"jade":159,"tickets":0}, income=[], reserve_pulls=2)
    result = run(value)
    assert result["options"][0]["scenarios"]["neutral"]["all_targets_probability"] == 0
    remaining = result["options"][-1]["scenarios"]["neutral"]["remaining_resources"]
    assert remaining["spendable_pulls"] == 0 and remaining["jade_remainder"] == 159
    value["parameters"]["budget"]["jade"] = -1
    with pytest.raises(CompanionError):
        run(value)


def test_unknown_future_banner_and_unknown_pity_are_not_invented():
    value = fixture("pull-plan")
    value["parameters"]["options"][0]["stages"][0].update(deadline=None,schedule_status="unknown")
    result = execute(value).to_dict()
    assert result["status"] == "partial" and result["missing_fields"]
    assert result["data"]["result"]["options"][0]["status"] == "missing_schedule"
    value = fixture("pull-plan")
    value["parameters"]["states"][0]["pity"] = None
    result = run(value)
    assert result["options"][0]["status"] == "missing_initial_state" and result["options"][-1]["id"] == "skip"


def test_dates_and_non_monotone_income_and_duplicate_states_are_invalid():
    for mutation in ("past", "income", "state", "stage"):
        value = fixture("pull-plan")
        p = value["parameters"]
        if mutation == "past":
            p["income"][0]["available_on"] = p["as_of"]
        elif mutation == "income":
            p["income"][0]["conservative"]["jade"] = 100000
        elif mutation == "state":
            p["states"].append(deepcopy(p["states"][0]))
        else:
            p["options"][1]["stages"][1]["id"] = "first"
        with pytest.raises(CompanionError):
            run(value)


def test_new_character_light_cone_and_eidolon_alternatives_keep_pools_separate():
    value = fixture("pull-plan")
    p = value["parameters"]
    p.update(income=[],budget={"jade":0,"tickets":1})
    p["states"] = [{"pool_type":"character","pity":89,"guaranteed":True}, {"pool_type":"light_cone","pity":0,"guaranteed":False}]
    for option in p["options"]:
        option["stages"] = [option["stages"][0]]
        option["stages"][0]["rules"] = "hsr-character-assumed"
    p["options"][1].update(id="cone",category="light_cone")
    p["options"][1]["stages"][0]["rules"] = "hsr-light-cone-assumed"
    eidolon = deepcopy(p["options"][0])
    eidolon.update(id="eidolon",category="eidolon")
    eidolon["stages"][0]["copies"] = 2
    p["options"].append(eidolon)
    result = run(value)
    probs = [o["scenarios"]["neutral"]["all_targets_probability"] for o in result["options"][:-1]]
    assert probs == pytest.approx([1, .008*.75, 0])
    assert p["states"][0]["pity"] == 89 and p["states"][1]["pity"] == 0


def test_numerical_benefit_is_recomputed_and_does_not_become_account_gain():
    value = fixture("pull-plan")
    left, right = fixture("damage"), fixture("damage")
    right["parameters"]["damage_bonus"] = 1
    value["parameters"]["options"][0]["benefit"] = {"kind":"fixed_state_damage", "description":"固定状态增伤对照", "baseline":left, "variant":right}
    result = run(value)["options"][0]["benefit"]
    assert result["baseline"] == 2025 and result["variant"] == 2700
    assert result["relative_delta"] == pytest.approx(1/3) and result["account_gain_percent"] is None
    value["parameters"]["options"][0]["benefit"]["variant"]["conditions"]["investment"] = "ideal_upper_bound"
    with pytest.raises(CompanionError) as exc:
        run(value)
    assert exc.value.code == "VERSION_INCOMPATIBLE"


def test_plan_compute_budget_is_shared_across_options_and_scenarios():
    value = fixture("pull-plan")
    value["budget"]["max_transitions"] = 2
    with pytest.raises(CompanionError) as exc:
        run(value)
    assert exc.value.code == "BUDGET_EXHAUSTED"
