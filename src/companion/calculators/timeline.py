"""Local action-gauge scheduler: speed changes preserve remaining distance."""
from copy import deepcopy
import math
import time

from companion.contracts import CompanionError, ErrorCode
from companion.experiments.contracts import check
from .resources import transact

GAUGE = 10000.0
EPS = 1e-9


def calculate(parameters, budget):
    check("timeline-parameters.schema.json", parameters)
    actors = deepcopy(parameters["actors"])
    ids = [a["id"] for a in actors]
    if len(set(ids)) != len(ids):
        raise CompanionError(ErrorCode.INVALID_INPUT, "时序角色 ID 重复")
    if parameters["sp"] > parameters["sp_cap"]:
        raise CompanionError(ErrorCode.INVALID_INPUT, "初始战技点超过上限")
    uncertain = []
    for actor in actors:
        if actor["energy"] > actor["energy_cap"]:
            raise CompanionError(ErrorCode.INVALID_INPUT, "初始能量超过上限")
        if actor.get("speed_precision") is not None:
            low, high = actor["speed"], actor["speed"] + actor["speed_precision"]
            uncertain.append({"actor": actor["id"], "speed_interval": [low, high],
                              "base_av_interval_without_scheduled_effects": [GAUGE / high, GAUGE / low]})
    if uncertain:
        return {"scope": "local_timeline", "events": [], "precision_ranges": uncertain,
                "termination": "insufficient_speed_precision", "exact_order_available": False}
    by_id = {a["id"]: a for a in actors}
    scheduled = sorted(enumerate(deepcopy(parameters["scheduled"])), key=lambda pair: (pair[1]["at"], pair[0]))
    for _, event in scheduled:
        if event["actor"] not in by_id:
            raise CompanionError(ErrorCode.INVALID_INPUT, "事件角色不存在")
    for actor in actors:
        actor.update(gauge=GAUGE, turn=0)
        for action in actor["rotation"]:
            for effect in action["effects"]:
                if effect["target"] not in by_id:
                    raise CompanionError(ErrorCode.INVALID_INPUT, "效果目标不存在")
    for _, event in scheduled:
        if event["kind"] == "ultimate":
            for effect in event["action"]["effects"]:
                if effect["target"] not in by_id:
                    raise CompanionError(ErrorCode.INVALID_INPUT, "效果目标不存在")
    shared = {"sp": parameters["sp"], "sp_cap": parameters["sp_cap"]}
    events, t, consumed = [], 0.0, set()
    deadline = time.monotonic() + budget["max_seconds"]
    horizon = min(parameters["until_av"], budget["max_av"])

    def effects(action):
        for effect in action["effects"]:
            target = by_id[effect["target"]]
            value = effect["value"]
            if effect["kind"] == "speed":
                target["speed"] = value
            elif effect["kind"] == "advance":
                target["gauge"] = max(0, target["gauge"] - GAUGE * value)
            elif effect["kind"] == "delay":
                target["gauge"] += GAUGE * value

    termination = "av_budget" if parameters["until_av"] > budget["max_av"] else "horizon"
    while True:
        if len(events) >= budget["max_events"]:
            termination = "event_budget"
            break
        if time.monotonic() >= deadline:
            termination = "time_budget"
            break
        turn_time = t + min(a["gauge"] / a["speed"] for a in actors)
        external = [(i, e) for i, e in scheduled if i not in consumed]
        external_time = external[0][1]["at"] if external else math.inf
        next_time = min(turn_time, external_time)
        if next_time > horizon + EPS:
            break
        dt = max(0, next_time - t)
        for actor in actors:
            actor["gauge"] = max(0, actor["gauge"] - actor["speed"] * dt)
        t = next_time
        # Explicit scheduled events precede natural turns at the same AV.
        if external_time <= turn_time + EPS:
            i, event = external[0]
            actor = by_id[event["actor"]]
            consumed.add(i)
            if event["kind"] == "ultimate":
                result = transact(actor, shared, event["action"])
                if result["executed"]:
                    effects(event["action"])
                events.append({"at": t, "actor": actor["id"], "kind": "ultimate", **result})
                if not result["executed"]:
                    termination = "resource_deficit"
                    break
            else:
                effects({"effects": [{"kind": event["kind"], "target": actor["id"], "value": event["value"]}]})
                events.append({"at": t, "actor": actor["id"], "kind": event["kind"], "value": event["value"],
                               "remaining_gauge": actor["gauge"], "executed": True})
            continue
        # Input order is an explicit tie-break assumption, not a game-client priority claim.
        actor = next(a for a in actors if a["gauge"] <= EPS)
        action = actor["rotation"][actor["turn"] % len(actor["rotation"])]
        result = transact(actor, shared, action)
        events.append({"at": t, "actor": actor["id"], "kind": action["kind"], **result})
        if not result["executed"]:
            termination = "resource_deficit"
            break
        actor["turn"] += 1
        actor["gauge"] = GAUGE
        effects(action)
    return {"scope": "local_timeline", "events": events, "termination": termination, "sp": shared["sp"],
            "energy": {a["id"]: a["energy"] for a in actors}, "until_av": horizon,
            "ordering": "scheduled events before normal turns at equal AV; scheduled input order then actor input order",
            "coverage": "no enemies, damage, buff expiry, extra turns, summons or special resources",
            "formula_source_ids": ["kqm-speed", "kqm-speed-proof"], "exact_order_available": True}
