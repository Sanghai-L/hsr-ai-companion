"""Finite-state DP, with absorbing success and independent pool identity."""
from collections import defaultdict
import math
import time

from companion.contracts import CompanionError, ErrorCode
from companion.experiments.contracts import check

OFFICIAL_PITY = "https://support.hoyoverse.com/hc/en-us/articles/50913710696217-How-does-the-pity-system-work-for-different-banners-and-reruns"
OFFICIAL_LC = "https://support.hoyoverse.com/hc/en-us/articles/50913708153625-How-does-the-guarantee-system-work-for-the-Light-Cone-Event-Warp-and-does-my-pity-carry-over"
CURVE_SOURCE = "https://gachaguide.com/honkai_star_rail_probabilities_deep_dive"


class WorkBudget:
    def __init__(self, budget):
        self.maximum = budget["max_transitions"]
        self.deadline = time.monotonic() + budget["max_seconds"]
        self.used = 0

    def spend(self, count=1):
        self.used += count
        if self.used > self.maximum or time.monotonic() > self.deadline:
            raise CompanionError(ErrorCode.BUDGET_EXHAUSTED, "概率状态递推达到预算；缩小目标或显式增加预算",
                                 details={"transitions": self.used})


def resolve_rules(spec):
    if isinstance(spec, str):
        if spec not in {"hsr-character-assumed", "hsr-light-cone-assumed"}:
            raise CompanionError(ErrorCode.UNSUPPORTED, "未知卡池规则")
        character = spec == "hsr-character-assumed"
        hard, base, start, step = (90, .006, 74, .06) if character else (80, .008, 66, .07)
        spec = {"id": spec + "-20261108", "pool_type": "character" if character else "light_cone", "hard_pity": hard,
                "featured_rate": .5 if character else .75,
                "hazards": [1.0 if n == hard else min(1.0, base + max(0, n-start+1)*step) for n in range(1, hard+1)],
                "curve_kind": "empirical_assumption", "source_refs": [OFFICIAL_PITY, OFFICIAL_LC, CURVE_SOURCE],
                "note": "经典限定池情景；基础率／硬保底取官方帮助，角色50%为公开卡池口径假设；逐抽线性软保底为经验假设，光锥65/66起点存在争议；不是当前全部卡池精确概率"}
    check("banner-rules.schema.json", spec)
    hazards = spec["hazards"]
    if len(hazards) != spec["hard_pity"] or hazards[-1] != 1:
        raise CompanionError(ErrorCode.INVALID_INPUT, "概率曲线长度须等于硬保底且最后一抽概率为 1")
    if spec["pool_type"] != "synthetic" and spec["curve_kind"] == "synthetic":
        raise CompanionError(ErrorCode.INVALID_INPUT, "真实卡池不可标为合成规则")
    return spec


def validate_state(state, rules):
    if state["pool_type"] != rules["pool_type"]:
        raise CompanionError(ErrorCode.INVALID_INPUT, "角色、光锥及合成卡池的保底状态不可混用")
    if state["pity"] is not None and state["pity"] >= rules["hard_pity"]:
        raise CompanionError(ErrorCode.INVALID_INPUT, "已垫抽数须小于硬保底；出五星后重置为 0")


def distribution(rules, pity, guaranteed, copies, work):
    hard, rate = rules["hard_pity"], rules["featured_rate"]
    maximum = hard * 2 * copies - pity
    states = {(pity, guaranteed, 0): 1.0}
    pmf = [0.0] * (maximum + 1)
    for pull in range(1, maximum + 1):
        following = defaultdict(float)
        for (counter, guarantee, owned), mass in states.items():
            work.spend()
            five = rules["hazards"][counter]
            win = 1.0 if guarantee else rate
            if five < 1:
                following[(counter+1, guarantee, owned)] += mass * (1-five)
            success = mass * five * win
            if owned + 1 == copies:
                pmf[pull] += success
            elif success:
                following[(0, False, owned+1)] += success
            lose = mass * five * (1-win)
            if lose:
                following[(0, True, owned)] += lose
        states = following
        if not states:
            pmf = pmf[:pull+1]
            break
    if states or not math.isclose(math.fsum(pmf), 1, abs_tol=1e-10):
        raise CompanionError(ErrorCode.INTERNAL_FAILURE, "概率质量校验未通过")
    return pmf


def summarize(pmf, pulls):
    probability = min(1.0, max(0.0, math.fsum(pmf[:pulls+1])))
    expected = math.fsum(i*p for i, p in enumerate(pmf))
    capped = math.fsum(i*p for i, p in enumerate(pmf[:pulls+1])) + pulls * (1-probability)
    cumulative, quantiles = 0.0, {}
    for n, mass in enumerate(pmf):
        cumulative += mass
        for q in (.5, .9, .95):
            if cumulative + 1e-12 >= q and str(q) not in quantiles:
                quantiles[str(q)] = n
    return {"success_probability": probability, "failure_probability": max(0.0, 1-probability),
            "expected_pulls_to_target": expected, "expected_spend_capped": capped,
            "quantiles": quantiles, "hard_maximum": len(pmf)-1, "probability_mass": math.fsum(pmf)}


def calculate(parameters, budget, *, work=None):
    check("gacha-parameters.schema.json", parameters)
    rules = resolve_rules(parameters["rules"])
    state = parameters["state"]
    validate_state(state, rules)
    work = work or WorkBudget(budget)
    pities = [state["pity"]] if state["pity"] is not None else [0, rules["hard_pity"]-1]
    if state["pity"] is None and any(a > b for a, b in zip(rules["hazards"], rules["hazards"][1:])):
        raise CompanionError(ErrorCode.MISSING_DATA, "非单调概率曲线无法用保底端点界定范围", details={"fields": ["state.pity"]})
    guarantees = [state["guaranteed"]] if state["guaranteed"] is not None else [False, True]
    pities = list(dict.fromkeys(pities))
    scenarios = []
    for pity in pities:
        for guarantee in guarantees:
            pmf = distribution(rules, pity, guarantee, parameters["copies"], work)
            result = {"initial_state": {"pool_type": rules["pool_type"], "pity": pity, "guaranteed": guarantee},
                      **summarize(pmf, parameters["pulls"])}
            if len(pities)*len(guarantees) == 1:
                result["first_hit_distribution"] = pmf
            scenarios.append(result)
    unknown = state["pity"] is None or state["guaranteed"] is None
    return {"scope": "target_acquisition", "rules": rules, "pulls": parameters["pulls"], "copies": parameters["copies"],
            "scenarios": scenarios, "state_unknown": unknown,
            "probability_range": [min(s["success_probability"] for s in scenarios), max(s["success_probability"] for s in scenarios)],
            "range_interpretation": "bounds over possible initial states; no prior distribution or guessed mean" if unknown else "known initial state",
            "inheritance": "pity and guarantee carry within the same declared pool type; other pools remain unchanged",
            "transitions": work.used, "curve_is_official_exact": False}
