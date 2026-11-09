"""Development-time lock creation. Runtime never downloads or relocks code."""
import hashlib
import json
from pathlib import Path

from companion.sim_backends.hsr_nous import tree_digest

ROOT = Path(__file__).resolve().parents[2]


def main():
    upstreams = json.loads((ROOT / "manifests/upstreams.lock.json").read_bytes())
    upstream = next(x for x in upstreams["upstreams"] if x["id"] == "hsr-nous")
    repo = ROOT / ".local/upstream/hsr-nous/repo"
    templates = ROOT / ".local/probes/simulation-templates"
    content = []
    for directory in ("src/hsr_nous/sim", "src/hsr_nous/sim_schema", "src/hsr_nous/common", "data/library"):
        content.append({"root": "repository", "path": directory, "kind": "tree",
                        "suffixes": [".py", ".yaml", ".json"],
                        "sha256": tree_digest(repo / directory, suffixes={".py", ".yaml", ".json"})})
    content.append({"root": "generated_templates", "path": ".", "kind": "tree", "suffixes": [".yaml"],
                    "sha256": tree_digest(templates, suffixes={".yaml"})})
    for relative in ("LICENSE", "src/hsr_nous/__init__.py"):
        content.append({"root": "repository", "path": relative, "kind": "file",
                        "sha256": hashlib.sha256((repo / relative).read_bytes()).hexdigest()})
    for relative in ("turnbasedgamedata/MonsterConfig.json", "turnbasedgamedata/MonsterTemplateConfig.json",
                     "turnbasedgamedata/MonsterSkillConfig.json", "turnbasedgamedata/EliteGroup.json", "turnbasedgamedata/HardLevelGroup.json"):
        content.append({"root": "data", "path": relative, "kind": "file",
                        "sha256": hashlib.sha256((ROOT / ".local/data-snapshot" / relative).read_bytes()).hexdigest()})
    lock = {"schema_version": 1, "backend": "hsr-nous", "commit": upstream["commit"],
            "repository": upstream["repository"], "license": "MIT; see licenses/HSR_Nous-MIT.txt",
            "patches": [{"path": p["path"], "sha256": p["sha256"]} for p in upstream["local_patches"]],
            "content_locks": content, "core_dependencies": "tools/p0/simulator-requirements.lock",
            "game_accuracy_certified": False, "distribution": "local pinned runtime; no third-party game data in wheel"}
    (ROOT / "manifests/simulator.lock.json").write_text(json.dumps(lock, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Locked existing backend and templates:", upstream["commit"], len(content), "components")


if __name__ == "__main__":
    main()
