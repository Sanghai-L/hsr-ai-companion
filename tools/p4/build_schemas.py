"""Build strict public simulation contracts: data only, never raw DSL."""
from record import write_json


def obj(fields, required=None):
    return {"type": "object", "properties": fields, "required": list(fields if required is None else required), "additionalProperties": False}


def integer(low, high):
    return {"type": "integer", "minimum": low, "maximum": high}


def number(low, high):
    return {"type": "number", "minimum": low, "maximum": high}


def string(maximum=200):
    return {"type": "string", "minLength": 1, "maxLength": maximum}


def array(item, minimum=0, maximum=30):
    return {"type": "array", "items": item, "minItems": minimum, "maxItems": maximum}


def nullable(schema):
    return {"anyOf": [schema, {"type": "null"}]}


def main():
    quantity = obj({"value": nullable(number(0, 1000000)), "basis": {"enum": ["base", "equipment_bonus", "public_panel"]},
                    "precision": nullable(number(0, 100)), "source_ref": string(2000)})
    skills = obj({"basic": integer(1, 7), "skill": integer(1, 15), "ultimate": integer(1, 15), "talent": integer(1, 15)})
    skills["description"] = "星魂加成前的技能等级；后端自行应用E3/E5。展示等级不经核对不能直接当作基础等级。"
    cone = obj({"entity_id": string(80), "instance_id": string(80), "level": integer(1, 80), "promotion": integer(0, 6),
                "superimposition": integer(1, 5), "path": string(40), "source_ref": string(2000)})
    relic = obj({"entity_id": string(80), "instance_id": string(80), "set_id": string(80),
                 "slot": {"enum": ["head", "hands", "body", "feet", "sphere", "rope"]},
                 "level": integer(0, 15), "rarity": integer(2, 5), "main_stat": string(80), "main_value": number(0, 1000000),
                 "sub_values": {"type": "object", "maxProperties": 4, "additionalProperties": number(0, 1000000)}, "source_ref": string(2000)})
    member = obj({"character_id": string(80), "form_id": string(100), "ownership": {"enum": ["owned", "not_owned", "unknown"]},
                  "level": integer(1, 80), "promotion": integer(0, 6), "eidolon": integer(0, 6), "skill_levels": skills,
                  "trace_policy": {"enum": ["all_unlocked", "partial", "unknown"]},
                  "light_cone": nullable(cone), "relics": array(relic, 0, 6),
                  "attributes": {"type": "object", "properties": {key: quantity for key in ("hp", "atk", "def", "spd", "crit_rate", "crit_dmg", "break_effect", "energy_regen", "effect_hit", "effect_res")}, "additionalProperties": False},
                  "source_refs": array(string(2000), 1, 30)})
    build = obj({"origin": {"enum": ["account", "manual", "hypothesis", "synthetic"]},
                 "snapshot_id": nullable(string(80)), "members": array(member, 4, 4), "assumptions": array(string(1500), 0, 30)})
    parameters = obj({"scenario_id": {"enum": ["alpha-moc"]}, "build": build,
                      "initial_resources": obj({"skill_points": integer(0, 5), "energy_ratio": number(0, 1),
                                                "techniques": array(string(100), 0, 4), "source_ref": string(2000)}),
                      "policy": obj({"id": {"enum": ["p0-bounded"]}, "skill_threshold": integer(0, 5), "support_target_form_id": nullable(string(100))}),
                      "mode": {"enum": ["roll", "expected"]}, "seed": integer(0, 2**32 - 1),
                      "precision": {"enum": ["model_diagnostic", "high"]}})
    for name, value in (("simulation-build", build), ("simulation-parameters", parameters)):
        write_json(f"schemas/{name}.schema.json", {"$schema": "https://json-schema.org/draft/2020-12/schema", **value})
    print("Built data-only simulation build and parameter contracts")


if __name__ == "__main__":
    main()
