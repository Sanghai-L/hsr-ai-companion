import copy
from pathlib import Path
import shutil

import pytest

from companion.contracts import CompanionError, canonical
from companion.knowledge.package import KnowledgePackage, MAX_PACKAGE, build_package

SOURCE = Path(__file__).resolve().parents[1] / "fixtures/knowledge/source"


def sample(version="0.1.0", **kwargs):
    return build_package(SOURCE, version=version, **kwargs)


def test_deterministic_package_and_complete_verification():
    first = sample()
    assert len(first.manifest["entries"]) == 3
    assert first.encode() == sample().encode()
    assert KnowledgePackage.decode(first.encode()).fingerprint == first.fingerprint


@pytest.mark.parametrize("mutation", ["traversal", "duplicate", "critical", "script", "hash", "extra", "agent"])
def test_bad_package_is_rejected(mutation):
    package = sample()
    value = copy.deepcopy({"manifest": package.manifest, "bodies": package.bodies})
    if mutation == "traversal":
        value["manifest"]["entries"][0]["body_path"] = "../personal/database"
    elif mutation == "duplicate":
        value["manifest"]["entries"].append(value["manifest"]["entries"][0])
    elif mutation == "critical":
        value["manifest"]["execute_rules"] = "evil"
    elif mutation == "script":
        value["bodies"]["combat/test-turn.md"] = "```python\nprint('no')\n```"
    elif mutation == "hash":
        value["manifest"]["files"][0]["sha256"] = "0" * 64
    elif mutation == "extra":
        value["bodies"]["evil.py"] = "no"
    elif mutation == "agent":
        value["manifest"]["entries"][0].update(id="AGENTS", body_path="combat/AGENTS.md", category="combat")
        value["bodies"]["combat/AGENTS.md"] = "instructions"
    with pytest.raises(CompanionError):
        KnowledgePackage.decode(canonical(value))


def test_oversize_and_unknown_source_file(tmp_path):
    with pytest.raises(CompanionError):
        KnowledgePackage.decode(b" " * (MAX_PACKAGE + 1))
    source = tmp_path / "source"
    shutil.copytree(SOURCE, source)
    (source / "AGENTS.md").write_text("not data", encoding="utf-8")
    with pytest.raises(CompanionError):
        build_package(source, version="0.1.0")

