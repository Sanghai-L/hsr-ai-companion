"""Fixed-state ordinary direct damage, Decimal arithmetic, explicit zones."""
from copy import deepcopy
from decimal import Decimal, localcontext

from companion.contracts import CompanionError, ErrorCode
from companion.experiments.contracts import check

D = lambda value: Decimal(str(value))


def settle(parameters):
    check("damage-parameters.schema.json", parameters)
    if parameters["damage_type"] != "direct":
        raise CompanionError(ErrorCode.UNSUPPORTED, "此公式只覆盖普通直伤；击破、持续、真实、欢愉伤害由后续机制处理")
    if parameters["stat"]["basis"] == "public_panel" and parameters["stat"]["equipment_bonus"] != 0:
        raise CompanionError(ErrorCode.INVALID_INPUT, "公开面板不可再次叠加装备")
    if parameters["stat"]["value"] is None:
        raise CompanionError(ErrorCode.MISSING_DATA, "结算属性未知", details={"fields": ["parameters.stat.value"]})
    if parameters["stat"].get("precision") is not None:
        raise CompanionError(ErrorCode.MISSING_DATA, "属性只有显示精度；请提供明确区间或精确假设", details={"fields": ["parameters.stat.exact_value_or_scenario"]})
    with localcontext() as ctx:
        ctx.prec = 36
        stat = D(parameters["stat"]["value"]) + D(parameters["stat"]["equipment_bonus"])
        base = stat * D(parameters["multiplier"]) + D(parameters["flat_damage"])
        reduction = min(D(1), D(parameters["def_reduction"]) + D(parameters["def_ignore"]))
        level = D(parameters["attacker_level"]) + 20
        defense = level / (level + (D(parameters["enemy_level"]) + 20) * (1 - reduction))
        effective_res = D(parameters["resistance"]) - D(parameters["res_penetration"])
        # Community and locked backend agree only on the interior; refuse disputed clamp extremes.
        if not D(-1) <= effective_res <= D("0.9"):
            raise CompanionError(ErrorCode.UNSUPPORTED, "有效抗性超出已核对范围 [-1,0.9]；不推断极端截断规则")
        crit_rate = max(D(0), min(D(1), D(parameters["crit_rate"])))
        crit = {"expected": 1 + crit_rate * D(parameters["crit_damage"]),
                "crit": 1 + D(parameters["crit_damage"]), "noncrit": D(1)}[parameters["crit_mode"]]
        zones = {"base_damage": base, "damage_bonus": 1 + D(parameters["damage_bonus"]),
                 "defense": defense, "resistance": 1 - effective_res,
                 "vulnerability": 1 + D(parameters["vulnerability"]), "crit": crit,
                 "toughness": D(1) if parameters["broken"] else D("0.9")}
        total = D(1)
        for value in zones.values():
            total *= value
        return {"value": float(total), "decimal_value": str(total), "unit": "damage",
                "zones": {key: float(value) for key, value in zones.items()},
                "scope": "fixed_state_direct_damage", "rounding": "36-digit Decimal; no intermediate integer rounding; no game display rounding claim",
                "formula_source_ids": ["kqm-damage", "nous-rulebook-crosscheck"],
                "verification": "source cross-check and independent hand calculation; not game-client calibration"}


def calculate(parameters):
    baseline = settle(parameters)
    if "change" not in parameters:
        return baseline
    change = parameters["change"]
    changed = deepcopy(parameters)
    changed.pop("change")
    changed[change["field"]] = change["value"]
    variant = settle(changed)
    delta = variant["value"] - baseline["value"]
    return {**baseline, "single_factor": {"field": change["field"], "before": parameters[change["field"]],
             "after": change["value"], "variant": variant, "absolute_delta": delta,
             "relative_delta": delta / baseline["value"] if baseline["value"] else None,
             "scope": "fixed state only; not full battle or account gain"}}
