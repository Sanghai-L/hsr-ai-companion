import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def fixture(name):
    return json.loads((ROOT / f"tests/fixtures/requests/{name}.json").read_bytes())["experiment"]
