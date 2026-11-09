"""Generate inspectable strict JSON schemas; no executable data in knowledge."""
from copy import deepcopy
from record import ROOT, write_json


def obj(properties, required=None):
    return {"type": "object", "properties": properties, "required": list(properties if required is None else required), "additionalProperties": False}


def number(low=0, high=1e12):
    return {"type": "number", "minimum": low, "maximum": high}


def integer(low=0, high=2000):
    return {"type": "integer", "minimum": low, "maximum": high}


def string(maximum=200):
    return {"type": "string", "minLength": 1, "maxLength": maximum}


def array(items, maximum=30, minimum=0):
    return {"type": "array", "items": items, "maxItems": maximum, "minItems": minimum}


def nullable(schema):
    return {"anyOf": [schema, {"type": "null"}]}


def enum(*values):
    return {"enum": list(values)}


def write(name, value):
    write_json("schemas/" + name + ".schema.json", {"$schema": "https://json-schema.org/draft/2020-12/schema", **value})


def main():
    conditions = obj({"game_version": string(40), "mode": string(100),
                      "investment": enum("real_account", "equal_investment", "ideal_upper_bound", "synthetic"),
                      "notes": string(2000), "snapshot_id": nullable(string(100))},
                     ["game_version", "mode", "investment", "notes"])
    versions = obj({key: string(200) for key in ("engine", "rules", "knowledge", "data")})
    from companion import __version__
    versions["properties"]["engine"]["description"] = "当前安装的执行版本，必须为 " + __version__
    versions["properties"]["rules"]["description"] = "当前受控计算规则版本，必须为 p3-1"
    budget = obj({"max_events": integer(1, 300), "max_av": {"type": "number", "exclusiveMinimum": 0, "maximum": 100000},
                  "max_transitions": integer(1, 3000000), "max_seconds": {"type": "number", "exclusiveMinimum": 0, "maximum": 30}})
    experiment = obj({"schema_version": {"const": 1}, "kind": enum("damage", "timeline", "gacha", "pull_plan", "simulation"),
                      "conditions": conditions, "versions": versions, "budget": budget,
                      "parameters": {"type": "object", "maxProperties": 40},
                      "assumptions": array(string(1500), 30), "source_refs": array(string(2000), 30, 1),
                      "run": obj({"task_id": string(100), "started_at": {"type": "string", "format": "date-time"}}, [])},
                     ["schema_version", "kind", "conditions", "versions", "budget", "parameters", "assumptions", "source_refs"])
    write("experiment", experiment)
    write("comparison", obj({"left": experiment, "right": experiment, "declaration": string(2000)}, ["left", "right"]))
    damage = obj({"damage_type": enum("direct", "dot", "break", "super_break", "true", "elation"),
                  "stat": obj({"value": nullable(number()), "unit": {"const": "flat"}, "basis": enum("public_panel", "base"),
                               "equipment_bonus": number(), "precision": nullable({"type": "number", "exclusiveMinimum": 0})},
                              ["value", "unit", "basis", "equipment_bonus"]),
                  "multiplier": number(0, 1000), "flat_damage": number(), "attacker_level": integer(1, 100),
                  "enemy_level": integer(1, 200), "damage_bonus": number(0, 100),
                  "def_reduction": number(0, 10), "def_ignore": number(0, 10),
                  "resistance": number(-1, 1), "res_penetration": number(0, 10),
                  "vulnerability": number(0, 100), "crit_rate": number(-10, 10), "crit_damage": number(0, 100),
                  "crit_mode": enum("expected", "crit", "noncrit"), "broken": {"type": "boolean"},
                  "change": obj({"field": enum("multiplier", "flat_damage", "damage_bonus", "def_reduction", "def_ignore",
                                               "resistance", "res_penetration", "vulnerability", "crit_rate", "crit_damage"),
                                 "value": number(-10, 1e12)})},
                 ["damage_type", "stat", "multiplier", "flat_damage", "attacker_level", "enemy_level", "damage_bonus", "def_reduction", "def_ignore",
                  "resistance", "res_penetration", "vulnerability", "crit_rate", "crit_damage", "crit_mode", "broken"])
    write("damage-parameters", damage)
    effect = obj({"kind": enum("speed", "advance", "delay"), "target": string(80), "value": number(0, 10000)})
    effect["allOf"] = [{"if": {"properties": {"kind": {"const": "speed"}}}, "then": {"properties": {"value": {"exclusiveMinimum": 0}}},
                         "else": {"properties": {"value": {"maximum": 10}}}}]
    action = obj({"kind": enum("basic", "skill", "ultimate"), "sp_cost": integer(0, 20), "sp_gain": integer(0, 20),
                  "energy_gain": number(0, 10000), "regen_applies": {"type": "boolean"},
                  "energy_cost": number(0, 10000), "effects": array(effect, 20)},
                 ["kind", "sp_cost", "sp_gain", "energy_gain", "regen_applies", "effects"])
    rotation = deepcopy(action)
    rotation["properties"]["kind"] = enum("basic", "skill")
    rotation["properties"]["energy_cost"] = {"const": 0}
    ultimate = deepcopy(action)
    ultimate["properties"]["kind"] = {"const": "ultimate"}
    ultimate["required"] = [*ultimate["required"], "energy_cost"]
    actor = obj({"id": string(80), "speed": {"type": "number", "exclusiveMinimum": 0, "maximum": 10000},
                 "speed_precision": nullable(number(0.000001, 100)), "energy": number(0, 10000), "energy_cap": number(0, 10000),
                 "energy_regen": number(0, 10), "rotation": array(rotation, 20, 1)},
                ["id", "speed", "energy", "energy_cap", "energy_regen", "rotation"])
    timed_effect = obj({"at": number(0, 100000), "actor": string(80), "kind": enum("speed", "advance", "delay"), "value": number(0, 10000)})
    timed_effect["allOf"] = deepcopy(effect["allOf"])
    event = {"oneOf": [timed_effect,
                       obj({"at": number(0, 100000), "actor": string(80), "kind": {"const": "ultimate"}, "action": ultimate})]}
    write("timeline-parameters", obj({"actors": array(actor, 8, 1), "sp": integer(0, 20), "sp_cap": integer(0, 20),
                                      "until_av": number(0, 100000), "scheduled": array(event, 100)}))
    rules = obj({"id": string(100), "pool_type": enum("character", "light_cone", "synthetic"), "hard_pity": integer(1, 100),
                 "featured_rate": number(0.00000001, 1), "hazards": array(number(0, 1), 100, 1),
                 "curve_kind": enum("synthetic", "explicit_assumption", "empirical_assumption"),
                 "source_refs": array(string(2000), 10, 1), "note": string(2000)})
    write("banner-rules", rules)
    state = obj({"pool_type": enum("character", "light_cone", "synthetic"), "pity": nullable(integer(0, 99)),
                 "guaranteed": nullable({"type": "boolean"})})
    gacha = obj({"rules": {"oneOf": [enum("hsr-character-assumed", "hsr-light-cone-assumed"), rules]},
                 "state": state, "pulls": integer(0, 2000), "copies": integer(1, 7)})
    write("gacha-parameters", gacha)
    amount = obj({"jade": integer(0, 10000000), "tickets": integer(0, 100000)})
    income = obj({"id": string(100), "available_on": {"type": "string", "format": "date"}, "source_ref": string(2000),
                  "conservative": amount, "neutral": amount, "optimistic": amount})
    stage = obj({"id": string(100), "deadline": nullable({"type": "string", "format": "date"}),
                 "schedule_status": enum("confirmed", "hypothetical", "unknown"),
                 "rules": gacha["properties"]["rules"], "copies": integer(1, 7)})
    benefit = obj({"kind": enum("qualitative", "fixed_state_damage"), "description": string(2000),
                   "baseline": experiment, "variant": experiment}, ["kind", "description"])
    option = obj({"id": string(100), "category": enum("new_character", "light_cone", "eidolon", "team_completion"),
                  "stages": array(stage, 5, 1), "benefit": benefit, "reversal_conditions": array(string(1500), 10, 1)})
    write("pull-plan-parameters", obj({"as_of": {"type": "string", "format": "date"}, "budget": amount,
                                       "reserve_pulls": integer(0, 2000), "income": array(income, 60),
                                       "states": array(state, 3, 1), "options": array(option, 5, 1),
                                       "preferences": array(string(1000), 20)}))
    print("Generated 7 strict P3 schemas")


if __name__ == "__main__":
    main()
