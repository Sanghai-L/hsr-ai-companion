"""Audit current P4 scope and available code without certifying new features."""
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
import uuid

from scope_audit import check_planning_baseline, compare_runtime_with_historical_wheel, probe_runtime, require_historical_finalizer_scope

ROOT = Path(__file__).resolve().parents[2]


def main():
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    output = ROOT / ".local/evidence/rechecks" / ("p4-v1.1-" + run_id)
    output.mkdir(parents=True)
    planning = check_planning_baseline(ROOT)
    wheel = compare_runtime_with_historical_wheel(ROOT)
    probes = probe_runtime(ROOT, ROOT / ".local/probes/scope-recheck" / run_id / "never-initialized-player")
    ledger = json.loads((ROOT / "docs/development/task-status.json").read_bytes())
    rows = ledger["tasks"]
    if [row["id"] for row in rows] != [f"D{i:03}" for i in range(1, 59)]:
        raise ValueError("task registry must contain all 58 unique sequential task IDs")
    tasks = {row["id"]: row for row in ledger["tasks"]}
    for task in rows:
        if task["status"] not in {"DONE", "IN_PROGRESS", "NOT_STARTED", "BLOCKED"}:
            raise ValueError("unknown task status")
        if any(dep not in tasks or dep >= task["id"] for dep in task["dependencies"]):
            raise ValueError("invalid or forward task dependency")
        if task["status"] == "DONE" and any(tasks[dep]["status"] != "DONE" for dep in task["dependencies"]):
            raise ValueError("completed task has an unfinished dependency")
    markdown = (ROOT / "docs/development/task-status.md").read_text(encoding="utf-8")
    markdown_states = []
    for line in markdown.splitlines():
        if re.match(r"^\| D\d{3} \|", line):
            fields = [field.strip() for field in line.split("|")]
            markdown_states.append((fields[1], fields[4]))
    if markdown_states != [(row["id"], row["status"]) for row in rows]:
        raise ValueError("JSON and Markdown task states disagree")
    ready = [row["id"] for row in rows if row["status"] != "DONE" and all(tasks[dep]["status"] == "DONE" for dep in row["dependencies"])]
    gate = json.loads((ROOT / "docs/gates/P4-alpha.json").read_bytes())
    catalog = json.loads((ROOT / "benchmarks/catalog.json").read_bytes())
    gaps = json.loads((ROOT / "manifests/simulator-gaps.json").read_bytes())
    metadata_conflicts = []
    for source, status in (("manifests/simulator-gaps.json:p4_followup", gaps.get("p4_followup", {}).get("status")),
                           ("benchmarks/catalog.json:p4_development", catalog.get("p4_development", {}).get("status"))):
        if status == "D038_BLOCKED" and tasks["D038"]["status"] == "IN_PROGRESS":
            metadata_conflicts.append({"source": source, "status": status, "ledger_status": tasks["D038"]["status"]})
    try:
        require_historical_finalizer_scope(ROOT)
        guard = {"blocks_old_scope_finalization": False}
    except RuntimeError as error:
        guard = {"blocks_old_scope_finalization": True, "message": str(error)}
    sys.path.insert(0, str(ROOT / "tools/p0"))
    from validate_p0 import validate
    try:
        validate(shared_only=True)
        historical_validator = {"result": "passed-original-immutable-baseline"}
    except ValueError as error:
        historical_validator = {"result": "historical-baseline-not-applicable-to-approved-revision", "reason": str(error)}
        if not str(error).startswith("Original plans unchanged"):
            raise
    report = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "scope_revision": planning["revision_id"],
              "planning": planning, "runtime_wheel_comparison": wheel, "runtime_probes": probes,
              "ledger_validation": {"task_count": len(rows), "done_dependencies_satisfied": True, "markdown_states_match": True,
                                    "next_executable_tasks": ready},
              "task_states": [{"id": task, "status": tasks[task]["status"], "scope_note": tasks[task].get("scope_note"),
                               "open_items": tasks[task].get("open_items", [])} for task in ("D035", "D036", "D037", "D038", "D039", "D040", "D041", "D042")],
              "gate": {"status": gate["status"], "manual_observation_required": gate.get("manual_observation_required"),
                       "previous_gate_retained": bool(gate.get("previous_gate"))},
              "metadata_conflicts": metadata_conflicts, "historical_finalizer_guard": guard,
              "historical_p0_validator": historical_validator,
              "conclusion": "SIMPLIFIED_SCOPE_REQUIRES_IMPLEMENTATION_NOT_PLAYER_OBSERVATION",
              "product_source_changed_by_this_audit": False, "alpha_passed": False}
    path = output / "report.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(path), "planning_revision": planning["revision_id"],
                      "runtime_files_checked": wheel["checked_files"], "runtime_files_changed": wheel["changed_files"],
                      "metadata_conflicts": metadata_conflicts, "task_states": [(x["id"], x["status"]) for x in report["task_states"]],
                      "alpha_passed": False}, ensure_ascii=False))


if __name__ == "__main__":
    main()
