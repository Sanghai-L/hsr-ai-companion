"""Sequential targets use spend distributions, never multiply full-budget odds."""
from collections import defaultdict
import math

from companion.contracts import CompanionError, ErrorCode
from companion.experiments.contracts import check, comparison, fingerprint, prepare
from companion.calculators import damage
from companion.calculators.gacha import WorkBudget, distribution, resolve_rules, validate_state
from .budget import SCENARIOS, available, validate_income


def benefit_result(benefit):
    if benefit["kind"] == "qualitative":
        if "baseline" in benefit or "variant" in benefit:
            raise CompanionError(ErrorCode.INVALID_INPUT, "定性收益不可附未经使用的数值实验")
        return {**benefit, "account_gain_percent": None}
    if "baseline" not in benefit or "variant" not in benefit:
        raise CompanionError(ErrorCode.MISSING_DATA, "数值收益需要双方可复算实验", details={"fields": ["benefit.baseline", "benefit.variant"]})
    left, right = prepare(benefit["baseline"]), prepare(benefit["variant"])
    if left["kind"] != "damage" or right["kind"] != "damage":
        raise CompanionError(ErrorCode.UNSUPPORTED, "P3 数值收益只接普通直伤固定状态公式")
    comparison(left, right)
    if "change" in left["parameters"] or "change" in right["parameters"]:
        raise CompanionError(ErrorCode.INVALID_INPUT, "收益比较须给出基准与变体本身，不嵌套边际比较")
    baseline = damage.calculate(left["parameters"])
    variant = damage.calculate(right["parameters"])
    delta = variant["value"] - baseline["value"]
    return {"kind": "fixed_state_damage", "description": benefit["description"], "baseline": baseline["value"], "variant": variant["value"],
            "relative_delta": delta/baseline["value"] if baseline["value"] else None,
            "baseline_fingerprint": fingerprint(left), "variant_fingerprint": fingerprint(right),
            "account_gain_percent": None, "scope": "fixed state only; not full battle or account-wide gain"}


def calculate(parameters, budget):
    check("pull-plan-parameters.schema.json", parameters)
    validate_income(parameters)
    states = {s["pool_type"]: s for s in parameters["states"]}
    if len(states) != len(parameters["states"]):
        raise CompanionError(ErrorCode.INVALID_INPUT, "同一卡池初始状态重复")
    ids = [o["id"] for o in parameters["options"]]
    if len(ids) != len(set(ids)) or "skip" in ids:
        raise CompanionError(ErrorCode.INVALID_INPUT, "方案 ID 重复或占用了保留 ID skip")
    work, options = WorkBudget(budget), []
    cache = {}
    for option in parameters["options"]:
        result = {"id": option["id"], "category": option["category"], "benefit": benefit_result(option["benefit"]),
                  "reversal_conditions": option["reversal_conditions"], "scenarios": {}, "status": "calculated"}
        stages = option["stages"]
        stage_ids = [s["id"] for s in stages]
        if len(stage_ids) != len(set(stage_ids)):
            raise CompanionError(ErrorCode.INVALID_INPUT, "同一方案的阶段 ID 重复")
        known = [s["deadline"] for s in stages if s["deadline"] is not None]
        if known != sorted(known):
            raise CompanionError(ErrorCode.INVALID_INPUT, "目标阶段截止日期顺序错误")
        if any(s["deadline"] is None or s["schedule_status"] == "unknown" for s in stages):
            result.update(status="missing_schedule", missing_fields=[f"options.{option['id']}.stages.deadline_or_confirmed_scenario"])
            options.append(result)
            continue
        hypothetical = any(s["schedule_status"] == "hypothetical" for s in stages)
        result["schedule_assumption"] = hypothetical
        resolved = [resolve_rules(stage["rules"]) for stage in stages]
        unknown = []
        for rules in resolved:
            pool = rules["pool_type"]
            if pool not in states:
                unknown.append("states." + pool)
            else:
                validate_state(states[pool], rules)
                if states[pool]["pity"] is None or states[pool]["guaranteed"] is None:
                    unknown.append("states." + pool + ".pity_or_guaranteed")
        if unknown:
            result.update(status="missing_initial_state", missing_fields=sorted(set(unknown)),
                          guidance="用 calculate/gacha 分别给出未知状态范围；连续目标计划需玩家明确初始状态，不能猜测")
            options.append(result)
            continue
        for scenario in SCENARIOS:
            spent, used_pools, reports = {0: 1.0}, set(), []
            for stage, rules in zip(stages, resolved):
                pool = rules["pool_type"]
                pity, guarantee = (0, False) if pool in used_pools else (states[pool]["pity"], states[pool]["guaranteed"])
                used_pools.add(pool)
                from companion.contracts import canonical
                key = (canonical(rules), pity, guarantee, stage["copies"])
                if key not in cache:
                    cache[key] = distribution(rules, pity, guarantee, stage["copies"], work)
                pmf = cache[key]
                resources = available(parameters, scenario, stage["deadline"])
                cap = resources["spendable_pulls"]
                following = defaultdict(float)
                for consumed, mass in spent.items():
                    for cost, chance in enumerate(pmf):
                        if not chance or consumed + cost > cap:
                            continue
                        work.spend()
                        following[consumed+cost] += mass * chance
                spent = following
                probability = min(1.0, max(0.0, math.fsum(spent.values())))
                reports.append({"stage_id": stage["id"], "deadline": stage["deadline"], "resources": resources,
                                "all_targets_so_far_probability": probability, "pool_type": pool,
                                "curve_kind": rules["curve_kind"], "rule_id": rules["id"]})
            success = min(1.0, max(0.0, math.fsum(spent.values())))
            expected_on_success = math.fsum(n*p for n, p in spent.items()) / success if success else None
            result["scenarios"][scenario] = {"all_targets_probability": success,
                "expected_spend_conditional_on_all_targets": expected_on_success,
                "minimum_remaining_on_success": reports[-1]["resources"]["total_pulls"] - max(spent) if spent else None,
                "stages": reports}
        options.append(result)
    final_date = max([parameters["as_of"], *[s["deadline"] for o in parameters["options"] for s in o["stages"] if s["deadline"]]])
    options.append({"id": "skip", "category": "do_not_pull", "status": "calculated", "benefit": {"kind": "qualitative", "description": "保留资源与后续选择；本轮不新增角色／光锥／星魂", "account_gain_percent": None},
                    "scenarios": {s: {"remaining_resources": available(parameters, s, final_date), "spend": 0} for s in SCENARIOS},
                    "reversal_conditions": ["已确认目标价值或偏好高于继续保留资源的价值时，可重新选择抽取方案"]})
    return {"scope": "resource_and_acquisition_plan", "options": options, "preferences": parameters["preferences"],
            "ranking": None, "ranking_reason": "抽取可达性与固定状态／定性收益分列；无整场或可比账号收益时不生成百分比总排名",
            "income_policy": "same source ID once; initial resources as-of date; future income gated by availability date; 160 jade per pull",
            "options_are_alternatives": True, "transitions": work.used}
