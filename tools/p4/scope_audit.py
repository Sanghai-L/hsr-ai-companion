"""Read-only scope checks. A revision is not a new implementation certificate."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path, PureWindowsPath
import zipfile


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def project_path(root, relative):
    path = PureWindowsPath(relative)
    if path.is_absolute() or path.drive or ".." in path.parts:
        raise ValueError("baseline paths must stay inside the project")
    candidate = Path(root).joinpath(*path.parts)
    if not candidate.resolve().is_relative_to(Path(root).resolve()):
        raise ValueError("baseline path escapes the project")
    return candidate


def check_planning_baseline(root):
    """Keep original hashes and compare current files to the approved revision."""
    root = Path(root)
    baseline = json.loads((root / "docs/requirements/baseline.json").read_bytes())
    historical = deepcopy(baseline["planning_hashes"])
    if digest(project_path(root, baseline["prd"])) != baseline["sha256"]:
        raise ValueError("original PRD checksum mismatch")
    revisions = baseline.get("planning_revisions", [])
    if revisions:
        revision = revisions[-1]
        if revision.get("decision") != baseline.get("current_scope_decision"):
            raise ValueError("current scope decision does not match the last approved revision")
        if not project_path(root, revision["decision"]).is_file():
            raise ValueError("approved scope decision is missing")
        expected = revision["planning_hashes"]
        if set(expected) != set(historical):
            raise ValueError("approved revision must identify the original planning documents")
        revision_id = revision["id"]
    else:
        if baseline.get("current_scope_decision"):
            raise ValueError("scope decision has no approved planning revision")
        expected = historical
        revision_id = "original"
    actual = {name: digest(project_path(root, name)) for name in expected}
    mismatches = [name for name in expected if actual[name] != expected[name]]
    if mismatches:
        raise ValueError("approved planning checksum mismatch: " + ", ".join(mismatches))
    return {"prd_matches_original": True, "revision_id": revision_id, "historical_hashes": historical,
            "approved_hashes": deepcopy(expected), "actual_hashes": actual,
            "current_files_match_original": actual == historical, "current_files_match_approved_revision": True}


def require_historical_finalizer_scope(root):
    """Stop the old P4 finalizer before it overwrites the user's revised scope."""
    baseline = json.loads((Path(root) / "docs/requirements/baseline.json").read_bytes())
    if baseline.get("current_scope_decision") or baseline.get("planning_revisions"):
        raise RuntimeError("旧P4收尾脚本只适用于原完整模拟范围；当前已有批准的范围修订。未写入记录。请按当前开发顺序验收，不可用历史结果重置D038或Alpha状态。")


def compare_runtime_with_historical_wheel(root):
    root = Path(root)
    summary = json.loads((root / ".local/evidence/D038/fresh-install-summary.json").read_bytes())
    wheel = Path(summary["wheel"])
    if not wheel.is_file() or digest(wheel) != summary["wheel_sha256"]:
        raise ValueError("historical installed wheel is missing or changed")
    changed, checked = [], []
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
        for directory, prefix, suffix in ((root / "src/companion", "companion/", ".py"),
                                          (root / "schemas", "companion/resources/schemas/", ".json")):
            for path in sorted(directory.rglob("*" + suffix)):
                if "__pycache__" in path.parts:
                    continue
                name = prefix + path.relative_to(directory).as_posix()
                checked.append(name)
                if name not in names or archive.read(name) != path.read_bytes():
                    changed.append(name)
        for name in names:
            if name.startswith("companion/") and name.endswith(".py") and not (root / "src" / name).is_file():
                changed.append(name)
    return {"checked_files": len(checked), "changed_files": sorted(set(changed)),
            "all_python_and_schema_files_match_historical_wheel": not changed,
            "historical_wheel_sha256": summary["wheel_sha256"]}


def probe_runtime(root, player_directory):
    """Observe actual available interfaces without starting a backend or UID call."""
    from companion.services.context import Context
    from companion.services.registry import Registry
    root, player_directory = Path(root), Path(player_directory)
    if player_directory.exists():
        raise ValueError("audit player directory must not exist")
    registry = Registry(Context(player_directory, offline=True))
    discovery = registry.invoke("simulation_schema", {}).to_dict()
    if discovery["status"] != "success":
        raise ValueError("existing simulation contract discovery failed")
    example = discovery["data"]["example_request"]
    schema = discovery["data"]["experiment_schema"]["properties"]["parameters"]

    def result_summary(result):
        return {"status": result.status, "error_code": result.error["code"] if result.error else None,
                "missing_fields": result.missing_fields}

    model = registry.invoke("simulation_preflight", deepcopy(example))
    high = deepcopy(example)
    high["experiment"]["parameters"]["precision"] = "high"
    high_result = registry.invoke("simulation_preflight", high)
    simplified = deepcopy(example)
    simplified["experiment"]["parameters"]["precision"] = "simplified"
    simplified_result = registry.invoke("simulation_preflight", simplified)
    minimal = deepcopy(example)
    del minimal["experiment"]["parameters"]["build"]["members"][0]["relics"]
    minimal_result = registry.invoke("simulation_preflight", minimal)
    unavailable = {name: {**result_summary(registry.invoke(name, {})), "registered": name in registry.operations}
                   for name in ("simulation_submit", "simulation_status", "simulation_result", "simulation_cancel", "simulation_compare", "experiment_replay")}
    calculators = {}
    for kind in ("damage", "timeline"):
        request = registry.invoke("calculation_schema", {"kind": kind})
        value = registry.invoke("calculate", request.data["example_request"])
        calculators[kind] = {**result_summary(value), "result_fingerprint": value.data.get("result_fingerprint") if value.data else None}
    if player_directory.exists():
        raise ValueError("read-only audit initialized player data")
    return {"precision_enum": schema["properties"]["precision"]["enum"],
            "parameter_fields": sorted(schema["properties"]), "available_simulation_tools": discovery["data"]["available"],
            "legacy_model_diagnostic": {**result_summary(model),
                "game_ranking_allowed": model.data.get("game_ranking_allowed") if model.data else None,
                "has_comparison_metrics": bool(model.data and any(key in model.data for key in ("expected_damage", "comparison", "rotation")))},
            "legacy_high_precision": result_summary(high_result), "simplified_precision_probe": result_summary(simplified_result),
            "omit_nonessential_equipment_probe": result_summary(minimal_result),
            "future_operations": unavailable, "reusable_calculators": calculators,
            "player_data_created": False, "uid_queries": 0, "backend_processes_started": 0,
            "scope": "current interface observations; not simplified comparison acceptance"}
