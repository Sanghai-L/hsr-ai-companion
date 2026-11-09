"""Bounded D038 investigation; always preserves the incomplete-scene label."""
from companion.contracts import canonical
from companion.modes.memory_of_chaos import FrozenMoc, outcome
from companion.sim_backends.hsr_nous import HsrNous
from record import ROOT, write_json
from copy import deepcopy
import hashlib
import json


def main():
    mode = FrozenMoc(ROOT / ".local/benchmarks/seed-scenario/scenario.json", ROOT / ".local/data-snapshot")
    report = mode.inspect()
    write_json(".local/evidence/D038/scene-audit.json", report)
    backend = HsrNous(python=ROOT / ".local/probes/hsr-nous/中文 空格验证/Scripts/python.exe",
                      repository=ROOT / ".local/upstream/hsr-nous/repo", data=ROOT / ".local/data-snapshot",
                      generated_templates=ROOT / ".local/probes/simulation-templates")
    example = json.loads((ROOT / "tests/fixtures/requests/simulation.json").read_bytes())["experiment"]
    results = []
    for team in ("team-a", "team-b"):
        value = deepcopy(example)
        value["parameters"]["build"] = json.loads((ROOT / f"tests/fixtures/builds/{team}.json").read_bytes())
        if team == "team-b":
            value["parameters"]["policy"]["support_target_form_id"] = None
        input_value = mode.backend_input(value, model_diagnostic=True)
        write_json(f".local/evidence/D038/{team}-input.json", input_value.to_dict())
        copies = []
        for index in (1, 2):
            output = backend.execute(input_value)
            write_json(f".local/evidence/D038/{team}-run-{index}.json", output)
            copies.append(output)
        same = copies[0] == copies[1]
        assert same, "same-seed diagnostic differed"
        results.append({"team": team, "same_seed_identical": same, "business_fingerprint": hashlib.sha256(canonical(copies[0])).hexdigest(),
                        "engine_outcome": outcome(copies[0]["termination"], truncated=copies[0]["snapshot"]["truncated"]),
                        "total_damage": copies[0]["snapshot"]["total_damage"], "current_wave": copies[0]["current_wave"],
                        "complete_supported": False, "game_ranking_allowed": False})
    write_json(".local/evidence/D038/diagnostic-summary.json", {"results": results, "complete_supported": False,
               "blockers": report["blockers"], "validation_level": "incomplete frozen-scene diagnostic, not full-scene acceptance"})
    print(json.dumps(results, ensure_ascii=False))


if __name__ == "__main__":
    main()
