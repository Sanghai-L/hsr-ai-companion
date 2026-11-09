"""Structural/permission checks, followed by a required separate semantic review."""
import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import re
import sqlite3

from companion.storage import Store
from tools.p6.record import write

ROOT = Path(__file__).resolve().parents[2]


def operation(item):
    return item["name"].rsplit("__",1)[-1]


def audit(plan_file):
    plan = json.loads(plan_file.read_bytes())
    folder = Path(plan["evidence"])
    records = [json.loads((folder/f"batch-{b:02}.json").read_bytes()) for b in range(1,11)]
    assert len({r["session_id"] for r in records}) == 10
    assert hashlib.sha256((ROOT/"evals/cases/release-50.json").read_bytes()).hexdigest() == plan["case_sha256"]
    assert hashlib.sha256((ROOT/"evals/rubric.md").read_bytes()).hexdigest() == plan["rubric_sha256"]
    case_tools, answers, failed_calls, commands = {}, {}, [], []
    batch_tools = {}
    for record in records:
        batch_tools[record["batch"]] = []
        assert record["exit_code"] == 0 and not record["timeout"] and record["usage"]
        rows = record["answers"]["results"]
        assert [r["id"] for r in rows] == record["cases"]
        answers.update({r["id"]: r["answer"] for r in rows})
        active = None
        for line in Path(record["raw_stdout"]).read_text(encoding="utf-8").splitlines():
            try: event = json.loads(line)
            except ValueError: continue
            item = event.get("item", {})
            if event.get("type") == "item.completed" and item.get("type") == "agent_message":
                match = re.search(r"CASE:(E\d{2})", item.get("text", ""))
                if match:
                    active = match[1]
            if event.get("type") == "item.completed" and item.get("type") == "mcp_tool_call":
                from tools.p5.verify_codex import extract_envelope
                tool = {"name": item.get("tool"), "arguments": item.get("arguments"), "envelope": extract_envelope(item)}
                case_tools.setdefault(active or "bootstrap", []).append(tool)
                batch_tools[record["batch"]].append(tool)
                if tool["envelope"].get("status") == "error":
                    failed_calls.append({"case": active, **tool})
            if event.get("type") == "item.completed" and item.get("type") == "command_execution":
                commands.append({"case": active, "command": item.get("command"), "exit_code": item.get("exit_code")})
    assert len(answers) == 50
    store = Store(Path(plan["data_dir"])/"personal", read_only=True)
    assert hashlib.sha256(store.read_research("eval-a", plan["old_research_id"]).encode()).hexdigest() == plan["old_body_sha256"]
    with store.connection() as connection:
        invariants = {"uid_queries": connection.execute("SELECT COUNT(*) FROM uid_queries").fetchone()[0],
                      "snapshots": connection.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0],
                      "program_confirmations": connection.execute("SELECT COUNT(*) FROM confirmations").fetchone()[0],
                      "applied_revisions": connection.execute("SELECT COUNT(*) FROM revision_plans WHERE state='applied'").fetchone()[0]}
    assert all(value == 0 for value in invariants.values()), invariants
    all_calls = [t for rows in batch_tools.values() for t in rows]
    assert not any(operation(t) in {"program_update_apply", "memory_revision_apply"} and t["envelope"].get("status") == "success" for t in all_calls)
    refreshes = [(batch, t) for batch, rows in batch_tools.items() for t in rows if operation(t) == "account_refresh"]
    assert refreshes and all(batch == 1 and t["envelope"].get("error", {}).get("code") == "NETWORK_FAILURE" for batch,t in refreshes)
    saves = [t for t in batch_tools[8] if operation(t) == "comparison_save" and t["envelope"].get("status") == "success"]
    replays = [t for t in batch_tools[9] if operation(t) == "experiment_replay" and t["envelope"].get("status") == "success"]
    assert saves and replays
    experiment_id = saves[-1]["envelope"]["data"]["experiment_id"]
    assert any(t["envelope"]["data"].get("experiment_id") == experiment_id and t["envelope"]["data"].get("same_result") for t in replays)
    expected = {"memory_of_chaos": {"dan-heng":9720,"herta":5940}, "pure_fiction":{"dan-heng":9720,"herta":24300},
                "apocalyptic_shadow":{"dan-heng":13230,"herta":7485}, "anomaly_arbitration":{"dan-heng":9720,"herta":12420}}
    for mode, numbers in expected.items():
        assert any((t["envelope"].get("data") or {}).get("mode") == mode and
                   {row["candidate_id"]:row["expected_damage"] for row in (t["envelope"].get("data") or {}).get("outcomes", [])} == numbers for t in batch_tools[6]), mode
    review_path = folder/"semantic-review.json"
    reviewed = False
    if review_path.exists():
        review = json.loads(review_path.read_bytes())
        assert {r["id"] for r in review["cases"]} == set(answers)
        assert review["critical_failures"] == 0 and sum(r["pass"] for r in review["cases"]) >= 45
        reviewed = True
    report = {"status": "PASS" if reviewed else "STRUCTURAL_PASS_REVIEW_PENDING", "plan": str(plan_file),
              "cases": 50, "actual_model_sessions": 10, "session_ids": [r["session_id"] for r in records],
              "permission_invariants": invariants, "old_body_unchanged": True, "saved_and_replayed_experiment": experiment_id,
              "case_tools": case_tools, "answers": answers, "failed_tool_calls": failed_calls, "shell_commands": commands,
              "semantic_review": str(review_path) if reviewed else None, "usage": [r["usage"] for r in records],
              "four_mode_numbers_verified": True, "model_selection": plan["model_selection"], "codex_version": plan["codex_version"],
              "trace_files": [str(folder/f"batch-{b:02}.stdout.jsonl") for b in range(1,11)]}
    write((folder/"audit.json").relative_to(ROOT), report)
    print(json.dumps({"status": report["status"], "cases": 50, "sessions": 10, "failed_tool_calls": len(failed_calls), "shell_command_count": len(commands),
                      "audit": str(folder/"audit.json")}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    audit(parser.parse_args().plan)
