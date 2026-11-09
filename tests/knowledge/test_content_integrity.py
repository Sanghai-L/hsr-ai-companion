import hashlib
import json
from pathlib import Path

import pytest
from companion.contracts import CompanionError
from companion.knowledge.package import build_package

ROOT = Path(__file__).resolve().parents[2]


def test_public_content_has_traceable_claims_and_no_private_data():
    package = build_package(ROOT / "knowledge", version="0.2.0")
    entries = package.manifest["entries"]
    assert len(entries) >= 30
    assert {"battle", "characters", "basics"} <= {e["category"] for e in entries}
    assert all(e["namespace"] == "release" for e in entries)
    sources = json.loads((ROOT / "knowledge/sources.json").read_bytes())["sources"]
    known = {s["url"]: s for s in sources}
    for entry in entries:
        assert entry["conditions"] and entry["exceptions"] and entry["claims"]
        assert len(package.bodies[entry["body_path"]]) > 100
        for claim in entry["claims"]:
            assert claim["source_ref"].split("#")[0] in known
            assert claim["source_sha256"] == known[claim["source_ref"].split("#")[0]]["sha256"]
            assert claim["locator"] and "not verified" in claim["verification"]
        assert "api/hsr/uid/" not in package.bodies[entry["body_path"]]
    assert {"phainon-fireseed", "cerydra-charge", "sunday-advance", "danheng-dragon", "acheron-stacks",
            "silverwolf-implant", "pela-dispel", "aventurine-followup"} <= {e["id"] for e in entries}


def test_retrieval_labels_are_frozen_and_refer_to_real_entries():
    dataset_path = ROOT / "evals/retrieval/queries.json"
    dataset = json.loads(dataset_path.read_bytes())
    queries = dataset["queries"]
    assert len(queries) >= 40
    assert len({q["id"] for q in queries}) == len(queries)
    assert sum(q["split"] == "validation" for q in queries) >= 10
    ids = {p.stem for p in (ROOT / "knowledge").glob("*/*.json")}
    assert all(set(q["relevant_ids"]) <= ids for q in queries)
    # A source-controlled checksum makes accidental relabelling visible in review.
    expected = (ROOT / "evals/retrieval/queries.sha256").read_text().strip()
    assert hashlib.sha256(dataset_path.read_bytes()).hexdigest() == expected


def test_extended_package_declares_actual_minimum_program_version():
    package = build_package(ROOT / "knowledge", version="0.2.0")
    assert package.compatible("0.1.1")
    assert not package.compatible("0.1.0")
    with pytest.raises(CompanionError):
        build_package(ROOT / "knowledge", version="0.2.0", program_min="0.1.0")
