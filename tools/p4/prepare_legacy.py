"""Run only with the pinned core Python: preserve D008's exact parsed input."""
import json
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[2]


def main():
    destination = ROOT / ".local/evidence/D035"
    destination.mkdir(parents=True, exist_ok=True)
    for team in ("team-a", "team-b"):
        value = {"build": yaml.safe_load((ROOT / f".local/evidence/D008/{team}-input.yaml").read_text(encoding="utf-8")),
                 "stage": yaml.safe_load((ROOT / ".local/evidence/D008/stage-input.yaml").read_text(encoding="utf-8")),
                 "seed": 42, "mode": "roll", "initial_sp": 3, "initial_energy_ratio": 0.5}
        (destination / f"{team}-legacy-input.json").write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Prepared exact P0 parsed inputs; no upstream or scenario changes")


if __name__ == "__main__":
    main()
