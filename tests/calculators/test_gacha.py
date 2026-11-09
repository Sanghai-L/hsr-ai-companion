from copy import deepcopy
import itertools
import math
import pytest

from companion.calculators.gacha import calculate, distribution, resolve_rules, WorkBudget
from companion.contracts import CompanionError
from companion.experiments.service import execute
from tests.experiments.helpers import fixture


def run(value):
    return calculate(value["parameters"], value["budget"])


@pytest.mark.parametrize("budget,expected", [(0,0), (1,.5), (2,1), (100,1)])
def test_literal_two_draw_tree_zero_and_budget(budget, expected):
    value = fixture("gacha")
    value["parameters"]["pulls"] = budget
    result = run(value)
    scenario = result["scenarios"][0]
    assert result["probability_range"] == [expected, expected]
    assert scenario["first_hit_distribution"] == [0,.5,.5]
    assert scenario["expected_pulls_to_target"] == 1.5
    assert scenario["quantiles"] == {"0.5":1,"0.9":2,"0.95":2}


def test_losing_featured_then_guaranteed_reset_and_multiple_copies():
    value = fixture("gacha")
    rules = value["parameters"]["rules"]
    rules.update(hard_pity=1, hazards=[1], featured_rate=.5)
    result = run(value)
    assert result["scenarios"][0]["first_hit_distribution"] == [0,.5,.5]
    value["parameters"].update(copies=2, pulls=3)
    assert run(value)["scenarios"][0]["first_hit_distribution"] == [0,0,.25,.5,.25]
    value["parameters"]["state"]["guaranteed"] = True
    assert run(value)["scenarios"][0]["first_hit_distribution"] == [0,0,.5,.5]


def exhaustive(rules, pity, guaranteed, copies):
    """Independent probability-tree enumeration; no state merging or DP calls."""
    pmf = {}
    def walk(n, counter, guarantee, got, mass):
        if got == copies:
            pmf[n] = pmf.get(n,0) + mass
            return
        probability = rules["hazards"][counter]
        win = 1 if guarantee else rules["featured_rate"]
        if probability < 1:
            walk(n+1, counter+1, guarantee, got, mass*(1-probability))
        if probability*win:
            walk(n+1,0,False,got+1,mass*probability*win)
        if probability*(1-win):
            walk(n+1,0,True,got,mass*probability*(1-win))
    walk(0,pity,guaranteed,0,1)
    return [pmf.get(n,0) for n in range(max(pmf)+1)]


@pytest.mark.parametrize("pity,guaranteed,copies", list(itertools.product(range(3), [False,True], [1,2])))
def test_dp_matches_independent_exhaustive_tree(pity, guaranteed, copies):
    value = fixture("gacha")
    rules = value["parameters"]["rules"]
    rules.update(hard_pity=3,hazards=[.25,.5,1],featured_rate=.75)
    actual = distribution(rules,pity,guaranteed,copies,WorkBudget(value["budget"]))
    assert actual == pytest.approx(exhaustive(rules,pity,guaranteed,copies), abs=1e-13)
    assert math.fsum(actual) == pytest.approx(1,abs=1e-12)


def test_unknown_pity_guarantee_returns_bounds_without_assumed_prior():
    value = fixture("gacha")
    value["parameters"]["state"].update(pity=None, guaranteed=None)
    result = execute(value).to_dict()
    assert result["status"] == "partial" and result["data"]["result"]["probability_range"] == [.5,1]
    assert len(result["missing_fields"]) == 2
    assert "mean" not in result["data"]["result"]


def test_hard_pity_guaranteed_and_independent_banner_states():
    value = fixture("gacha")
    for spec, pool, maximum in [("hsr-character-assumed","character",90),("hsr-light-cone-assumed","light_cone",80)]:
        value["parameters"].update(rules=spec,state={"pool_type":pool,"pity":maximum-1,"guaranteed":True})
        assert run(value)["probability_range"] == [1,1]
    value["parameters"]["state"]["pool_type"] = "character"
    with pytest.raises(CompanionError, match="混用"):
        run(value)


def test_invalid_curve_and_transition_budget_are_errors():
    value = fixture("gacha")
    value["parameters"]["rules"]["hazards"] = [.5,.9]
    with pytest.raises(CompanionError):
        run(value)
    value = fixture("gacha")
    value["budget"]["max_transitions"] = 1
    with pytest.raises(CompanionError) as exc:
        run(value)
    assert exc.value.code == "BUDGET_EXHAUSTED"


def test_builtin_curve_keeps_its_empirical_label_and_official_sources():
    rules = resolve_rules("hsr-light-cone-assumed")
    assert rules["curve_kind"] == "empirical_assumption" and rules["featured_rate"] == .75
    assert rules["hazards"][-1] == 1 and any("support.hoyoverse.com" in ref for ref in rules["source_refs"])
