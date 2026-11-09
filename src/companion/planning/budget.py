"""Resource ledger counts each source once and never assumes future banners."""
from datetime import date

from companion.contracts import CompanionError, ErrorCode

SCENARIOS = ("conservative", "neutral", "optimistic")


def validate_income(parameters):
    ids = [row["id"] for row in parameters["income"]]
    if len(ids) != len(set(ids)):
        raise CompanionError(ErrorCode.INVALID_INPUT, "收入来源 ID 重复，拒绝重复计入")
    occurrences = [(row["source_ref"], row["available_on"]) for row in parameters["income"]]
    if len(occurrences) != len(set(occurrences)):
        raise CompanionError(ErrorCode.INVALID_INPUT, "同一来源同日收入重复；不同奖励须给出可区分的来源引用")
    for row in parameters["income"]:
        if row["available_on"] <= parameters["as_of"]:
            raise CompanionError(ErrorCode.INVALID_INPUT, "收入须在预算快照日之后；已到账资源应计入起始预算")
        equivalents = [row[s]["jade"] + row[s]["tickets"] * 160 for s in SCENARIOS]
        if equivalents != sorted(equivalents):
            raise CompanionError(ErrorCode.INVALID_INPUT, "收入情景须按保守、中性、乐观递增")


def available(parameters, scenario, deadline):
    if deadline < parameters["as_of"]:
        raise CompanionError(ErrorCode.INVALID_INPUT, "目标截止日期早于预算快照")
    rows = [r for r in parameters["income"] if r["available_on"] <= deadline]
    jade = parameters["budget"]["jade"] + sum(r[scenario]["jade"] for r in rows)
    tickets = parameters["budget"]["tickets"] + sum(r[scenario]["tickets"] for r in rows)
    pulls = tickets + jade // 160
    usable = max(0, pulls - parameters["reserve_pulls"])
    return {"jade": jade, "tickets": tickets, "total_pulls": pulls, "jade_remainder": jade % 160,
            "spendable_pulls": usable, "reserve_pulls": parameters["reserve_pulls"], "included_income_ids": [r["id"] for r in rows]}
