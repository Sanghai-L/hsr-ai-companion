"""Extract every required mechanism from input, never from caller assertions."""
from collections import Counter
from copy import deepcopy
import hashlib
import json

from companion.contracts import CompanionError, ErrorCode, ToolResult, canonical
from companion import __version__
from companion.experiments.contracts import prepare, check
from companion.resources import resource_text


class CoverageRegistry:
    def __init__(self, value=None):
        self.value = deepcopy(value) if value is not None else json.loads(resource_text("manifests", "coverage.json"))
        self.entries = {}
        for entry in self.value["entries"]:
            if (entry["key"] in self.entries or entry["status"] not in {"verified", "approximate", "unsupported", "unknown"}
                    or not entry.get("reason") or not entry.get("impact") or not entry.get("validation_cases")):
                raise CompanionError(ErrorCode.VERSION_INCOMPATIBLE, "机制覆盖清单缺少明确状态、原因或证据")
            self.entries[entry["key"]] = entry
        self.fingerprint = hashlib.sha256(canonical(self.value)).hexdigest()

    def required(self, experiment):
        parameters = experiment["parameters"]
        scenario_id = parameters["scenario_id"]
        scenario = self.value["scenarios"].get(scenario_id)
        if scenario is None:
            raise CompanionError(ErrorCode.UNSUPPORTED, "场景没有覆盖登记")
        keys = {f"scenario:{scenario_id}:lineup", f"scenario:{scenario_id}:historical_rules"}
        keys.update("system:" + name for name in ("action_order", "skill_points", "energy", "critical_roll", "direct_damage", "break", "death", "wave_transition", "cycle_boundary"))
        paths = []
        for member in parameters["build"]["members"]:
            cid, form = member["character_id"], member["form_id"]
            keys.add("character:" + form)
            # E0 is required too; higher ranks include every active lower rank.
            keys.update(f"eidolon:{cid}:{rank}" for rank in range(member["eidolon"] + 1))
            keys.add(f"traces:{cid}:{member['trace_policy']}")
            paths.append(self.value["character_paths"].get(form))
            if member["light_cone"] is not None:
                cone = member["light_cone"]
                keys.add(f"light_cone:{cone['entity_id']}:s{cone['superimposition']}")
            sets = Counter(relic["set_id"] for relic in member["relics"])
            for set_id, count in sets.items():
                for pieces in (2, 4):
                    if count >= pieces:
                        keys.add(f"relic:{set_id}:{pieces}pc")
            if member["relics"]:
                keys.add("system:relic_attributes")
        for eid in scenario["enemy_ids"]:
            keys.update(f"enemy:{eid}:{part}" for part in ("stats", "resistance", "ai", "phase"))
        active = any(path in {"Rogue", "Mage", "Hunt", "Erudition"} for path in paths) or None in paths
        keys.add(f"scenario:{scenario_id}:turbulence:" + ("active" if active else "inactive"))
        if parameters["initial_resources"]["techniques"]:
            keys.add("system:techniques")
        return sorted(keys)

    def inspect(self, experiment):
        value = prepare(experiment)
        if value["kind"] != "simulation":
            raise CompanionError(ErrorCode.INVALID_INPUT, "预检需要 simulation 实验")
        check("simulation-parameters.schema.json", value["parameters"])
        scenario = self.value["scenarios"][value["parameters"]["scenario_id"]]
        if value["conditions"]["mode"] != "memory-of-chaos" or value["conditions"]["game_version"] != scenario["game_version"]:
            raise CompanionError(ErrorCode.VERSION_INCOMPATIBLE, "实验条件与冻结场景的模式／版本不一致")
        if value["conditions"]["investment"] == "real_account":
            build_input = value["parameters"]["build"]
            if build_input["origin"] != "account" or build_input["snapshot_id"] != value["conditions"]["snapshot_id"]:
                raise CompanionError(ErrorCode.CONFLICT, "真实账号投资口径与构筑快照不一致")
        from .builds import validate_build
        build = validate_build(value["parameters"]["build"])
        checks = []
        for key in self.required(value):
            entry = self.entries.get(key, {"key": key, "status": "unknown", "reason": "没有机制登记，不能当作已支持",
                                          "impact": "对可行性与排序的影响未知", "validation_cases": [], "model_executable": False, "critical": True})
            checks.append(deepcopy(entry))
        limitations = [item for item in checks if item["status"] != "verified"]
        complete = not limitations and not build["limitations"]
        certified = complete and self.value["game_accuracy_certified"]
        executable = all(item["model_executable"] for item in checks) and build["executable"]
        warnings = [f"{item['key']}：{item['reason']}；影响：{item['impact']}" for item in limitations]
        warnings.extend(build["limitations"])
        if value["parameters"]["mode"] == "expected":
            warnings.append("期望暴击仅供校准／初筛，不预测击杀时机与通关轮次")
        return {"required_mechanisms": [item["key"] for item in checks], "checks": checks,
                "coverage_fingerprint": self.fingerprint, "build": build,
                "complete_supported": complete, "game_accuracy_certified": certified,
                "can_execute_model_diagnostic": executable, "game_ranking_allowed": certified and value["parameters"]["mode"] == "roll",
                "precision": "high" if certified else "engineering_approximation", "warnings": warnings,
                "missing_fields": build["missing_fields"]}


def preflight(experiment, *, coverage=None):
    report = (coverage or CoverageRegistry()).inspect(experiment)
    value = experiment["parameters"]
    warnings = report.pop("warnings")
    if value["precision"] == "high" and not report["game_accuracy_certified"]:
        return ToolResult.failure(CompanionError(ErrorCode.UNSUPPORTED, "缺少关键机制或外部校准，拒绝高精度模拟", details={
            "mechanisms": [item["key"] for item in report["checks"] if item["status"] != "verified"]}),
            data=report, warnings=warnings, missing_fields=report["missing_fields"])
    return ToolResult(status="partial" if not report["complete_supported"] else "success", data=report,
                      warnings=warnings, assumptions=list(experiment["assumptions"]), missing_fields=report["missing_fields"],
                      versions={"engine": __version__, "data_commit": (coverage or CoverageRegistry()).value["backend_commit"]})


def inspect_build_structure(build):
    """Structural checks available before the account importer (D037)."""
    check("simulation-build.schema.json", build)
    forms, characters, instances = set(), set(), set()
    for member in build["members"]:
        if member["form_id"] in forms or member["character_id"] in characters:
            raise CompanionError(ErrorCode.INVALID_INPUT, "同一队伍不能重复占用角色或形态")
        if not member["form_id"].startswith(member["character_id"] + ":"):
            raise CompanionError(ErrorCode.INVALID_INPUT, "形态 ID 与角色不匹配")
        forms.add(member["form_id"])
        characters.add(member["character_id"])
        slots = [r["slot"] for r in member["relics"]]
        if len(slots) != len(set(slots)):
            raise CompanionError(ErrorCode.CONFLICT, "同一角色重复占用遗器槽位")
        for equipment in ([member["light_cone"]] if member["light_cone"] else []) + member["relics"]:
            instance = equipment["instance_id"]
            if instance in instances:
                raise CompanionError(ErrorCode.CONFLICT, "同一装备实例不能被重复占用", details={"instance_id": instance})
            instances.add(instance)
    if build["origin"] == "account" and not build["snapshot_id"]:
        raise CompanionError(ErrorCode.MISSING_DATA, "账号构筑需要不可变快照 ID", details={"fields": ["snapshot_id"]})
    if build["origin"] in {"hypothesis", "synthetic"} and not build["assumptions"]:
        raise CompanionError(ErrorCode.MISSING_DATA, "假设／合成构筑必须写明假设", details={"fields": ["assumptions"]})
    return {"executable": True, "limitations": [], "missing_fields": []}
