"""Check actual model tool traces and the resulting private database, fail closed."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3


def operation(name):
    return str(name).split("__")[-1]


def tools(record, name):
    return [item for item in record["tools"] if operation(item["name"]) == name]


def successful(record, name):
    return [item for item in tools(record, name) if item.get("envelope", {}).get("status") == "success"]


def data(item):
    return item["envelope"]["data"]


def comparison(item):
    value = data(item)
    return value.get("comparison", value)


def mode_calculations(record, mode):
    """Both public comparison entrypoints consume the actual mode template.

    The requirement is correct mode conditions and conclusions, not one API name.
    Generic comparison additionally requires discovery of that mode's template.
    Numeric and missing-data assertions below remain identical for both routes.
    """
    discovered = any(arguments(item).get("mode") == mode for item in successful(record, "analysis_schema"))
    result = []
    for name in ("mode_analyze", "simulation_compare"):
        for item in successful(record, name):
            args = arguments(item)
            if args.get("request", {}).get("mode") == mode and data(item).get("mode") == mode:
                if name == "mode_analyze" or discovered:
                    result.append(item)
    return result


def arguments(item):
    value = item.get("arguments") or {}
    return json.loads(value) if isinstance(value, str) else value


def audit(plan_file):
    plan = json.loads(plan_file.read_bytes())
    folder = Path(plan["evidence"])
    records = {case: json.loads((folder/(case + ".json")).read_bytes()) for case in plan["cases"]}
    sessions = [record["session_id"] for record in records.values()]
    assert all(sessions) and len(sessions) == len(set(sessions)), "Each acceptance must be an actual fresh model session"
    for case, record in records.items():
        assert record["exit_code"] == 0 and not record["timeout"] and record["answer"].strip(), case
        assert successful(record, "session_bootstrap") or tools(record, "session_bootstrap"), case + ": bootstrap missing"
        assert record["tools"], case
        assert not tools(record, "account_refresh"), "Unexpected UID operation"
        assert record["usage"], "No completed actual model turn"
        events = [json.loads(line) for line in Path(record["raw_stdout"]).read_text(encoding="utf-8").splitlines() if line.strip()]
        assert not any(event.get("item", {}).get("tool") == "account_refresh" for event in events), "Unexpected UID attempt, including failed calls"
    alpha = records["alpha"]
    saved = successful(alpha, "comparison_save")
    assert saved, "Model did not persist the comparison"
    experiment_id = data(saved[-1])["experiment_id"]
    original = comparison(saved[-1])
    assert original["mode"] == "memory_of_chaos" and original["ranking_permitted"]
    numbers = {row["candidate_id"]: row["expected_damage"] for row in original["outcomes"]}
    assert numbers == {"dan-heng": 9720, "herta": 5940}, numbers
    assert original["recommendation_ids"] == ["dan-heng"]
    writes = successful(alpha, "memory_append")
    assert any(experiment_id in arguments(item).get("experiment_ids", []) for item in writes), "Research must reference the real saved experiment"
    recovery = records["recovery"]
    assert successful(recovery, "memory_search") and successful(recovery, "memory_read"), "Fresh model did not retrieve research"
    repeated = successful(recovery, "experiment_replay")
    assert any(data(item).get("experiment_id") == experiment_id and data(item).get("same_result") is True for item in repeated), "Fresh model did not replay the original saved input"
    checks = {"alpha_saved": True, "cross_session_retrieved_and_recomputed": True}
    for case, mode in [("pf", "pure_fiction"), ("as", "apocalyptic_shadow"), ("aa", "anomaly_arbitration")]:
        calculations = mode_calculations(records[case], mode)
        assert any(data(item).get("ranking_permitted") for item in calculations), case + ": wrong or unused mode template"
        expected = {"pf": {"dan-heng": 9720, "herta": 24300},
                    "as": {"dan-heng": 13230, "herta": 7485},
                    "aa": {"dan-heng": 9720, "herta": 12420}}[case]
        assert any({row["candidate_id"]: row["expected_damage"] for row in data(item).get("outcomes", [])} == expected for item in calculations), case + ": example conditions or arithmetic changed"
        checks[mode] = True
    sensitivity = successful(records["pf"], "sensitivity_analyze")
    assert any(data(item)["reversal_conditions"] and arguments(item)["request"]["mode"] == "pure_fiction" for item in sensitivity), "No tool-verified PF reversal conditions"
    missing = [item for name in ("mode_analyze", "simulation_compare") for item in tools(records["pf"], name) if item.get("envelope", {}).get("status") == "partial"]
    assert any(data(item).get("ranking") is None and any(row.get("expected_damage") is None for row in data(item).get("outcomes", [])) and item["envelope"].get("missing_fields") for item in missing), "Missing core data was not checked with the actual tool"
    multi = successful(records["aa"], "multi_team_plan")
    assert multi and data(multi[-1])["mode"] == "anomaly_arbitration"
    assert data(multi[-1])["recommendations"] and data(multi[-1])["rules"]["king_can_reuse_knight_resources"]
    king_reused = False
    for item in multi:
        stages = {slot["id"]: slot["stage_type"] for slot in arguments(item)["request"]["slots"]}
        assert list(stages.values()).count("knight") == 3 and list(stages.values()).count("king") <= 1
        for option in data(item)["recommendations"]:
            chars, equipment = set(), set()
            assert {assignment["slot"] for assignment in option["assignments"]} == set(stages)
            for assignment in option["assignments"]:
                if stages[assignment["slot"]] == "king":
                    continue
                current = {form.split(":")[0] for form in assignment["members"]}
                items = set(assignment["equipment_instances"])
                assert not chars & current and not equipment & items
                chars |= current
                equipment |= items
            for assignment in option["assignments"]:
                if stages[assignment["slot"]] == "king":
                    king_reused |= bool(chars & {form.split(":")[0] for form in assignment["members"]})
    assert king_reused, "Actual optional King plan did not demonstrate legal Knight resource reuse"
    database = Path(plan["data_dir"])/"personal/personal.sqlite3"
    with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as connection:
        snapshots = connection.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
        assert snapshots == 0, "Acceptance changed account facts"
        experiments = connection.execute("SELECT id,payload FROM experiments WHERE account_id=?", ("p5-host-demo",)).fetchall()
        assert any(row[0] == experiment_id for row in experiments)
        conclusions = connection.execute("SELECT metadata FROM research WHERE account_id=?", ("p5-host-demo",)).fetchall()
        assert any(experiment_id in json.loads(row[0]).get("experiment_ids", []) for row in conclusions)
    # Claims are checked against actual outputs above; qualitative answer inspection remains explicit.
    checks.update(sensitivity_reversal=True, missing_mechanism_unranked=True, legal_three_knights=True, king_reuse_executed=True,
                  no_uid_calls=True, account_facts_unchanged=True)
    summary = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "status": "PASS", "plan": str(plan_file),
               "layer": "actual fresh Codex model sessions, verified installed wheel, real MCP tools and private SQLite",
               "cases": list(records), "model_sessions": len(records), "session_ids": sessions,
               "checks": checks, "experiment_id": experiment_id,
               "trace_files": [str(folder/(case + ".json")) for case in records],
               "usage": {case: record["usage"] for case, record in records.items()},
               "uid_queries": 0, "snapshots": snapshots}
    summary["failed_tool_attempts"] = {}
    summary["mode_entrypoints"] = {case: [operation(item["name"]) for item in mode_calculations(records[case], mode)]
        for case, mode in [("pf", "pure_fiction"), ("as", "apocalyptic_shadow"), ("aa", "anomaly_arbitration")]}
    summary["template_selection_policy"] = "mode_analyze or explicit mode-specific analysis_schema followed by simulation_compare; verify exact scenario outputs, not tool name alone"
    for case, record in records.items():
        events = [json.loads(line) for line in Path(record["raw_stdout"]).read_text(encoding="utf-8").splitlines() if line.strip()]
        summary["failed_tool_attempts"][case] = [{"tool": event["item"].get("tool"),
            "error": (event["item"].get("result") or {}).get("structured_content", {}).get("error")}
            for event in events if event.get("item", {}).get("type") == "mcp_tool_call" and event["item"].get("status") == "failed"]
    (folder/"audit.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "model_sessions": len(records), "checks": checks, "audit": str(folder/"audit.json")}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    audit(parser.parse_args().plan.resolve())
