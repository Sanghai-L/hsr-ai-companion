"""Extract identity/path metadata from the pinned MIT template library."""
import json
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[2]


def main():
    library = ROOT / ".local/upstream/hsr-nous/repo/data/library"
    cones, relics = {}, []
    for path in sorted((library / "light_cones").glob("*.yaml")):
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
        cones[str(value["light_cone_id"])] = value["path"]
    for path in sorted((library / "relics").glob("*.yaml")):
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
        relics.append(str(value["relic_set_id"]))
    value = {"schema_version": 1, "source_commit": "f8935ddb407b297732fbd3c624d55897e3e648b9",
             "source": "MIT template identity metadata; numeric game data excluded", "light_cone_paths": cones, "relic_sets": sorted(set(relics))}
    (ROOT / "manifests/build-catalog.json").write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Extracted template identity/path metadata:", len(cones), "cones,", len(set(relics)), "sets; this is not mechanism coverage")


if __name__ == "__main__":
    main()
