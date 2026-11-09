"""Small candidate-set enumeration with character/form/instance occupancy checks."""
from itertools import product
import math
import time

from companion.contracts import CompanionError, ErrorCode, ToolResult
from companion.experiments.contracts import check
from companion.modes.anomaly_arbitration import RULES
from companion.simulation.compare import compare
from companion.simulation.rotation import digest, prepare


def resources(candidate):
    return {"character": {m["character_id"] for m in candidate["members"]},
            "equipment": {instance for m in candidate["members"] for instance in m["equipment_instances"]}}


def conflicts(slots, choices, mode):
    result = []
    occupied = {}
    for slot, candidate in zip(slots, choices):
        # King is an independent challenge and may reuse any Knight resources.
        if mode == "anomaly_arbitration" and slot["stage_type"] == "king":
            continue
        for kind, values in resources(candidate).items():
            for value in sorted(values):
                key = (kind, value)
                if key in occupied:
                    result.append({"kind": kind, "resource": value, "slots": [occupied[key], slot["id"]]})
                occupied[key] = slot["id"]
    return result


def plan(request, *, clock=time.monotonic):
    check("multi-team.schema.json", request)
    deadline = clock() + request["max_seconds"]
    mode, slots, roster = request["mode"], request["slots"], request["roster"]
    if len({s["id"] for s in slots}) != len(slots):
        raise CompanionError(ErrorCode.CONFLICT, "多队关卡编号重复")
    kinds = [slot["stage_type"] for slot in slots]
    if mode == "anomaly_arbitration":
        if kinds.count("knight") != 3 or kinds.count("king") > 1 or "side" in kinds:
            raise CompanionError(ErrorCode.INVALID_INPUT, "异相分配需要三个骑士，可附一个可复用资源的王棋")
    elif kinds != ["side", "side"]:
        raise CompanionError(ErrorCode.INVALID_INPUT, "该模式分配两个独立半场")
    candidate_sets, metrics, unquantified = [], [], []
    sources, slot_evidence = {}, []
    common = None
    for slot in slots:
        value = prepare(slot["request"])
        if value["mode"] != mode:
            raise CompanionError(ErrorCode.INVALID_INPUT, "多队槽位使用了错误模式")
        basis = (value["game_version"], value["data_version"], value["method"])
        if common is not None and basis != common:
            raise CompanionError(ErrorCode.VERSION_INCOMPATIBLE, "多队候选版本不同，不能合并排名")
        common = basis
        for candidate in value["candidates"]:
            held = resources(candidate)
            missing = (held["character"] - set(roster["available_character_ids"])) | (held["equipment"] - set(roster["available_equipment_instances"]))
            if missing:
                raise CompanionError(ErrorCode.MISSING_DATA, "候选使用了假设可用清单以外的资源", details={"fields": sorted(missing)})
        result = compare(value, cancelled=lambda: clock() >= deadline)
        sources.update({source["ref"]: source for source in result.sources})
        slot_evidence.append({"slot": slot["id"], "input_fingerprint": result.data["input_fingerprint"],
                              "assumptions": result.assumptions, "warnings": result.warnings})
        if result.data["ranking"] is None:
            unquantified.append(slot["id"])
        metrics.append({row["candidate_id"]: row["expected_damage"] for row in result.data["outcomes"] if row["status"] == "completed"})
        candidate_sets.append(value["candidates"])
    visited, feasible, rejected, solutions = 0, 0, [], []
    total = math.prod(len(candidates) for candidates in candidate_sets)
    for choices in product(*candidate_sets):
        if visited >= request["max_combinations"] or clock() >= deadline:
            break
        visited += 1
        clash = conflicts(slots, choices, mode)
        if clash:
            rejected.extend(clash[:max(0, 30-len(rejected))])
            continue
        feasible += 1
        if unquantified:
            continue
        ratios, assignments = [], []
        for slot, candidate, scores in zip(slots, choices, metrics):
            score = scores[candidate["id"]]
            best = max(scores.values())
            ratios.append(score / best if best else 1)
            assignments.append({"slot": slot["id"], "candidate_id": candidate["id"], "members": [m["form_id"] for m in candidate["members"]],
                                "equipment_instances": sorted(resources(candidate)["equipment"]), "expected_damage": score,
                                "fraction_of_slot_candidate_best": ratios[-1]})
        solutions.append({"assignments": assignments, "weakest_slot_ratio": min(ratios), "sum_slot_ratios": math.fsum(ratios)})
    complete = visited == total and not unquantified
    solutions.sort(key=lambda row: (-row["weakest_slot_ratio"], -row["sum_slot_ratios"],
                                   tuple(a["candidate_id"] for a in row["assignments"])))
    return ToolResult(status="success" if complete and feasible else "partial",
                      data={"mode": mode, "scope": "given_candidate_sets_only", "input_fingerprint": digest(request),
                            "feasible_combinations": feasible, "visited_combinations": visited, "total_combinations": total,
                            "search_complete": visited == total, "unquantified_slots": unquantified,
                            "recommendations": solutions[:5] if complete else [],
                            "conflicting_resources": rejected,
                            "no_solution": visited == total and feasible == 0,
                            "replacement_direction": "为冲突槽位换用未占用角色或另一件装备实例；不复用受限资源",
                            "objective": "先最大化各槽位相对本槽候选最佳值的最小比例，再比较比例总和；不合计异口径伤害为通关分数",
                            "rules": RULES if mode == "anomaly_arbitration" else {"unique_character_and_equipment_between_sides": True},
                            "slot_evidence": slot_evidence,
                            "resource_claim": roster},
                      sources=list(sources.values()), versions=result.versions,
                      assumptions=[roster["notes"]], warnings=["只对明确假设可用清单与候选集推荐，不声称全局最优；每队辅助／生存短板仍需定性复核"])
