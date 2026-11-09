"""Freeze source-aligned candidates and private name-only roster selections."""
import argparse
import hashlib
import json
from pathlib import Path

from companion.modes.scenario_candidate import resolve_character, select_floor
from record import ROOT, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", type=Path, required=True)
    args = parser.parse_args()
    selection = json.loads(args.selection.read_bytes())
    evidence = ROOT / ".local/evidence/D038/current-1036-11"
    collection = json.loads((evidence / "collection.json").read_bytes())
    if collection["live_source_marker"] is None or not all(r["status"] == 200 for r in collection["records"]):
        raise RuntimeError("current scene is not source-aligned; retain candidate-only state")
    for record in collection["records"]:
        if hashlib.sha256((evidence / record["name"]).read_bytes()).hexdigest() != record["sha256"]:
            raise RuntimeError("collected source changed after observation")
    rows = json.loads((evidence / "period-1036.json").read_bytes())
    names = json.loads((evidence / "monster.json").read_bytes())
    candidate = select_floor(rows, names, floor=selection["floor"], period_id="1036", game_version=collection["live_source_marker"],
                             source_refs=[r["url"] for r in collection["records"]],
                             source_hashes={r["name"]: r["sha256"] for r in collection["records"]}, region=selection.get("region"))
    candidate["user_selected_name"] = selection["period_name"]
    characters = json.loads((ROOT / ".local/data-snapshot/starrailres/index_new/cn/characters.json").read_bytes())
    library = ROOT / ".local/upstream/hsr-nous/repo/data/library/characters"
    rosters = {}
    for side, selected in selection["teams"].items():
        team = [resolve_character(name, characters, aliases={"刻律德拉": "刻律德菈"}) for name in selected]
        if len(team) != 4 or len({m["character_id"] for m in team}) != 4:
            raise ValueError("selected team needs four distinct entities")
        for member in team:
            templates = [path.name for path in library.glob(member["character_id"] + "_*.yaml") if not path.name.endswith("_legacy.yaml")]
            member.update(template_candidates=templates, template_present=bool(templates),
                          mechanism_coverage="unknown", initial_resources="unknown", evidence_basis="user-selected name only")
        rosters[side] = team
    output = ".local/benchmarks/user-selected-moc-1036-11"
    write_json(output + "/scenario-candidate.json", candidate)
    write_json(output + "/selected-rosters.json", {"teams": rosters, "scope": "selection only; no UID/account write/build-level inference",
               "manual_test_status": "DEFERRED_BY_USER", "gameplay_observations": [], "calibration_completed": False})
    write_json(".local/evidence/D038/current-1036-11/preparation-summary.json", {"source_aligned": True,
               "live_source_marker": collection["live_source_marker"], "scenario_candidate_fingerprint": candidate["candidate_fingerprint"],
               "floor": candidate["floor"], "sides": list(candidate["sides"]),
               "unavailable_template_ids": [m["character_id"] for team in rosters.values() for m in team if not m["template_present"]],
               "manual_test_status": "DEFERRED_BY_USER", "complete_supported": False, "game_accuracy_certified": False,
               "blockers": ["enemy AI/phase and turbulence execution not verified", "one selected character has no canonical backend template",
                            "actual investment/build fields unknown", "manual observations deferred by user"]})
    print(json.dumps({"status": "SOURCE_ALIGNED_CANDIDATE_ONLY", "floor": candidate["floor"], "sides": list(candidate["sides"]),
                      "missing_templates": [m["character_id"] for team in rosters.values() for m in team if not m["template_present"]],
                      "manual_test_status": "DEFERRED_BY_USER"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
