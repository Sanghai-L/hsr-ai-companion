"""Immutable build import; no UID query, account edits or equipment guessing."""
from copy import deepcopy
from decimal import Decimal
import hashlib
import json

from companion.contracts import CompanionError, ErrorCode, ToolResult, canonical
from companion.experiments.contracts import check
from companion.resources import resource_text
from .preflight import inspect_build_structure

MAIN_STATS = {
    "head": {"hp"}, "hands": {"atk"},
    "body": {"hp_pct", "atk_pct", "def_pct", "crit_rate", "crit_dmg", "effect_hit", "heal_bonus"},
    "feet": {"hp_pct", "atk_pct", "def_pct", "spd"},
    "sphere": {"hp_pct", "atk_pct", "def_pct", "physical_dmg", "fire_dmg", "ice_dmg", "thunder_dmg", "wind_dmg", "quantum_dmg", "imaginary_dmg"},
    "rope": {"hp_pct", "atk_pct", "def_pct", "break_effect", "energy_regen"}}
SUB_STATS = {"hp", "atk", "def_", "hp_pct", "atk_pct", "def_pct", "spd", "crit_rate", "crit_dmg", "effect_hit", "effect_res", "break_effect"}


def speed_range(attribute):
    value, precision = attribute["value"], attribute["precision"]
    if value is None or precision is None:
        return {"display_value": value, "lower": None, "upper": None, "exact": False,
                "reason": "速度数值或显示精度未知，无法给可信有限区间；需精确值或明确舍入假设"}
    if precision == 0:
        return {"display_value": value, "lower": value, "upper": value, "exact": True, "reason": "输入明确声明精确值"}
    value, precision = Decimal(str(value)), Decimal(str(precision))
    return {"display_value": float(value), "lower": float(max(Decimal(0), value - precision)), "upper": float(value + precision),
            "exact": False, "reason": "未指定舍入方式，保守使用显示值±一个精度单位；不当作精确配速"}


def validate_build(build):
    report = inspect_build_structure(build)
    paths = json.loads(resource_text("manifests", "coverage.json"))["character_paths"]
    catalog = json.loads(resource_text("manifests", "build-catalog.json"))
    limitations, unsupported, missing, uncertainty, audit = [], [], [], {}, []
    for index, member in enumerate(build["members"]):
        prefix = f"members.{index}"
        cid, form = member["character_id"], member["form_id"]
        if form not in paths:
            unsupported.append(prefix + ".form_id")
            limitations.append(form + "：未登记的角色／加强形态，禁止自动混用默认模板")
        if build["origin"] in {"account", "manual"} and member["ownership"] != "owned":
            missing.append(prefix + ".ownership")
        if member["level"] != 80 or member["promotion"] != 6:
            unsupported.extend([prefix + ".level_scaling", prefix + ".promotion_scaling"])
            limitations.append(form + "：锁定角色模板的白值固定在80级满突破，不能只改等级标签冒充缩放")
        if member["trace_policy"] != "all_unlocked":
            unsupported.append(prefix + ".trace_policy")
            limitations.append(form + "：锁定模板没有选择性关闭小行迹的绑定接口")
        cone = member["light_cone"]
        if cone is not None:
            actual_path = catalog["light_cone_paths"].get(cone["entity_id"])
            if actual_path is None:
                unsupported.append(prefix + ".light_cone.entity_id")
                limitations.append(form + "：光锥不在锁定模板身份目录中")
            elif actual_path != cone["path"]:
                raise CompanionError(ErrorCode.INVALID_INPUT, "填写的光锥命途与锁定模板身份不一致")
            if form in paths and cone["path"] != paths[form]:
                raise CompanionError(ErrorCode.INVALID_INPUT, "角色与光锥命途不匹配", details={"form_id": form})
            if cone["level"] != 80 or cone["promotion"] != 6:
                unsupported.append(prefix + ".light_cone.level_scaling")
                limitations.append(form + "：当前光锥模板只固定80级满突破白值")
        for relic in member["relics"]:
            if relic["set_id"] not in catalog["relic_sets"]:
                unsupported.append(prefix + ".relics.set_id")
                limitations.append(form + "：遗器套装不在锁定模板身份目录中")
            if relic["main_stat"] not in MAIN_STATS[relic["slot"]] or set(relic["sub_values"]) - SUB_STATS:
                raise CompanionError(ErrorCode.INVALID_INPUT, "遗器词条与槽位不匹配或副词条未知")
            if relic["main_stat"] in relic["sub_values"]:
                raise CompanionError(ErrorCode.INVALID_INPUT, "遗器主副词条不能相同")
            if relic["rarity"] != 5 and relic["level"] > (relic["rarity"] - 2) * 3 + 6:
                raise CompanionError(ErrorCode.INVALID_INPUT, "遗器强化等级超过该星级上限")
        if "spd" in member["attributes"]:
            uncertainty[form] = speed_range(member["attributes"]["spd"])
            if not uncertainty[form]["exact"]:
                limitations.append(form + "：速度精度不足，不能直接用于精确行动顺序")
                missing.append(prefix + ".attributes.spd.precision")
        for stat, attribute in member["attributes"].items():
            audit.append({"form_id": form, "stat": stat, **attribute,
                          "usage": "validation_only" if attribute["basis"] == "public_panel" else "unsupported_override"})
            if attribute["basis"] != "public_panel":
                unsupported.append(prefix + ".attributes." + stat)
                limitations.append(form + "：模板引用不接受白值／装备属性覆盖，不能静默忽略手工数值")
        if any(a["basis"] == "public_panel" for a in member["attributes"].values()):
            limitations.append(form + "：展示面板只作核对依据，不作为基础属性再次叠加装备；尚未完成面板校准")
    report.update(executable=not unsupported and not missing, limitations=list(dict.fromkeys(limitations)),
                  unsupported_fields=sorted(set(unsupported)), missing_fields=sorted(set(missing)), speed_ranges=uncertainty,
                  attribute_audit=audit, build_fingerprint=hashlib.sha256(canonical(build)).hexdigest())
    return report


def to_backend_build(build, policy):
    """Return only accepted DSL fields; unsupported bindings fail explicitly."""
    if (not isinstance(policy, dict) or set(policy) != {"id", "skill_threshold", "support_target_form_id"}
            or policy["id"] != "p0-bounded" or type(policy["skill_threshold"]) is not int or not 0 <= policy["skill_threshold"] <= 5
            or (policy["support_target_form_id"] is not None and not isinstance(policy["support_target_form_id"], str))):
        raise CompanionError(ErrorCode.INVALID_INPUT, "只接受已登记策略及其结构化参数")
    report = validate_build(build)
    if not report["executable"]:
        raise CompanionError(ErrorCode.MISSING_DATA if report["missing_fields"] else ErrorCode.UNSUPPORTED,
                             "构筑尚不能无损绑定到锁定后端", details={"fields": report["missing_fields"], "unsupported_fields": report["unsupported_fields"]})
    forms = {m["form_id"] for m in build["members"]}
    target = policy["support_target_form_id"]
    if target is not None and target not in forms:
        raise CompanionError(ErrorCode.INVALID_INPUT, "辅助目标必须属于本队")
    team = []
    for member in build["members"]:
        converted = {"character_template": member["character_id"], "level": member["level"], "eidolon": member["eidolon"],
                     "skill_levels": deepcopy(member["skill_levels"])}
        if member["light_cone"] is not None:
            cone = member["light_cone"]
            converted.update(light_cone_template=cone["entity_id"], light_cone={"superimposition": cone["superimposition"]})
        if member["relics"]:
            converted["relics"] = {r["slot"]: {"set_id": r["set_id"], "main": r["main_stat"], "main_value": r["main_value"],
                                                   "subs": {stat: 0 for stat in r["sub_values"]}, "sub_values": deepcopy(r["sub_values"])}
                                    for r in member["relics"]}
        # Public panel values deliberately do not enter base_stats.
        team.append(converted)
    target_rules = []
    if target is not None:
        if target != "1408:base":
            raise CompanionError(ErrorCode.UNSUPPORTED, "当前已验证的P0辅助目标规则仅支持白厄；需要另行核验目标选择器")
        target_rules = [{"condition": "true", "selector": {"type": "has_modifier", "modifier_id": "TRACE_1408103"}}]
    return {"build": {"team": team, "policy": {"name": "p0-bounded-rule-policy", "action_rules": [
        {"condition": "energy >= max_energy", "action": "ultimate", "priority": 90},
        {"condition": f"skill_points > {policy['skill_threshold']}", "action": "skill", "priority": 50},
        {"condition": "true", "action": "basic", "priority": 0}], "target_rules": target_rules, "parameters": {}}}}


def import_snapshot(snapshot, form_ids, *, overrides=None, hypothesis=False, assumptions=()):
    """Assemble an independent draft; absence of gear never means unequipped."""
    check("account-snapshot.schema.json", snapshot)
    if len(form_ids) != 4 or len(set(form_ids)) != 4:
        raise CompanionError(ErrorCode.INVALID_INPUT, "需要四个互不重复的角色形态")
    overrides = deepcopy(overrides or {})
    if set(overrides) - set(form_ids):
        raise CompanionError(ErrorCode.INVALID_INPUT, "手工补充包含本队以外的形态")
    if hypothesis and not assumptions:
        raise CompanionError(ErrorCode.MISSING_DATA, "假设构筑必须写明独立假设", details={"fields": ["assumptions"]})
    declared = {c["form_id"]: c for c in snapshot["characters"]}
    fields = {}
    for field in snapshot["fields"]:
        key = field["entity_id"], field["field_id"]
        if key in fields:
            raise CompanionError(ErrorCode.CONFLICT, "快照包含同一实体的重复字段")
        fields[key] = field
    missing, draft, questions = [], [], []
    for index, form in enumerate(form_ids):
        source = declared.get(form)
        cid = source["character_id"] if source else form.split(":", 1)[0]
        if source is None and not hypothesis:
            missing.append(f"members.{index}.ownership")
        member = {"character_id": cid, "form_id": form, "ownership": source["ownership"] if source else "unknown",
                  "source_refs": ["snapshot:" + snapshot["snapshot_id"]], "attributes": {}}
        entity = "character:" + form
        for key, target in (("level", "level"), ("promotion", "promotion"), ("rank", "eidolon")):
            field = fields.get((entity, key))
            if field and field["quantity"]["state"] == "known":
                if field["quantity"]["unit"] != "count" or field["basis"] != "record":
                    raise CompanionError(ErrorCode.INVALID_INPUT, "角色等级／星魂需要计数单位和记录来源")
                member[target] = field["quantity"]["value"]
        for stat in ("hp", "atk", "def", "spd", "crit_rate", "crit_dmg", "break_effect", "energy_regen", "effect_hit", "effect_res"):
            field = fields.get((entity, stat))
            if field and field["basis"] in {"base", "equipment_bonus", "public_panel"}:
                q = field["quantity"]
                expected = "speed" if stat == "spd" else "flat" if stat in {"hp", "atk", "def"} else "ratio"
                if q["unit"] not in ({"ratio", "percent", "percentage_point"} if expected == "ratio" else {expected}):
                    raise CompanionError(ErrorCode.INVALID_INPUT, "账号属性单位不匹配", details={"field": stat})
                factor = 100 if q["unit"] in {"percent", "percentage_point"} else 1
                member["attributes"][stat] = {"value": q["value"] / factor if q["value"] is not None else None,
                                              "precision": q["precision"] / factor if q["precision"] is not None else None,
                                              "basis": field["basis"], "source_ref": field["source"]["ref"]}
        supplied = overrides.get(form, {})
        allowed = {"ownership", "level", "promotion", "eidolon", "skill_levels", "trace_policy", "light_cone", "relics", "attributes", "source_refs"}
        if not isinstance(supplied, dict) or set(supplied) - allowed:
            raise CompanionError(ErrorCode.INVALID_INPUT, "手工构筑字段未知；不能上传执行规则或改变形态")
        if supplied and (not supplied.get("source_refs") or (not hypothesis and supplied.get("ownership", member["ownership"]) != member["ownership"])):
            raise CompanionError(ErrorCode.MISSING_DATA, "独立手工补充需要来源；持有变化请先更新账号或明确假设", details={"fields": [form + ".source_refs"]})
        member.update(supplied)
        for key in ("level", "promotion", "eidolon", "skill_levels", "trace_policy", "light_cone", "relics"):
            if key not in member:
                missing.append(f"members.{index}.{key}")
        if member["ownership"] != "owned" and not hypothesis:
            missing.append(f"members.{index}.ownership")
        per_member = [key.rsplit(".", 1)[-1] for key in missing if key.startswith(f"members.{index}.")]
        if per_member:
            questions.append({"form_id": form, "fields": list(dict.fromkeys(per_member)),
                              "prompt": f"请补充 {form} 的 " + "、".join(dict.fromkeys(per_member)) + "；没有装备也请明确说明。"})
        draft.append(member)
    build = {"origin": "hypothesis" if hypothesis else "account", "snapshot_id": snapshot["snapshot_id"],
             "members": draft, "assumptions": list(assumptions)}
    report = validate_build(build) if not missing else None
    if report:
        missing.extend(report["missing_fields"])
        for path in report["missing_fields"]:
            index = int(path.split(".")[1])
            if not any(q["form_id"] == form_ids[index] for q in questions):
                questions.append({"form_id": form_ids[index], "fields": [path], "prompt": "请补充该构筑的精度／持有依据：" + path})
    return {"build": build if report is not None else None, "draft": build, "missing_fields": sorted(set(missing)),
            "questions": questions, "validation": report, "account_modified": False,
            "source_snapshot_fingerprint": hashlib.sha256(canonical(snapshot)).hexdigest(), "source_versions": deepcopy(snapshot["versions"])}


def import_result(snapshot, form_ids, **kwargs):
    report = import_snapshot(snapshot, form_ids, **kwargs)
    warnings = report["validation"]["limitations"] if report["validation"] else []
    return ToolResult(status="partial" if report["missing_fields"] or warnings or not report["validation"] or not report["validation"]["executable"] else "success", data=report,
                      missing_fields=report["missing_fields"], warnings=warnings, versions={"snapshot": snapshot["snapshot_id"]},
                      assumptions=list(kwargs.get("assumptions", ())))
