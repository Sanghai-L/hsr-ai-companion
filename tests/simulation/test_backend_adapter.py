import importlib
import json
from pathlib import Path
import subprocess

import pytest

from companion.contracts import CompanionError, ErrorCode
from companion.sim_backends.base import BackendInput
from companion.sim_backends.hsr_nous import HsrNous, tree_digest

ROOT = Path(__file__).resolve().parents[2]


def installed_backend():
    return HsrNous(python=ROOT / ".local/probes/hsr-nous/中文 空格验证/Scripts/python.exe",
                   repository=ROOT / ".local/upstream/hsr-nous/repo", data=ROOT / ".local/data-snapshot",
                   generated_templates=ROOT / ".local/probes/simulation-templates")


def legacy_input(team):
    # YAML is parsed only by the isolated core runtime, not by the main app.
    # D035 verifier stores the exact P0 dictionaries after parsing there.
    value = json.loads((ROOT / f".local/evidence/D035/{team}-legacy-input.json").read_bytes())
    return BackendInput(**value)


@pytest.mark.parametrize("team", ["team-a", "team-b"])
def test_formal_adapter_matches_all_frozen_p0_business_events(team):
    backend = installed_backend()
    result = backend.execute(legacy_input(team))
    original = json.loads((ROOT / f".local/evidence/D008/{team}-run-1.json").read_bytes())
    for field in ("snapshot", "events", "log", "damage_samples", "caveats"):
        assert result[field] == original[field], field
    assert result["backend_version"]["commit"] == "f8935ddb407b297732fbd3c624d55897e3e648b9"
    assert result["backend_version"]["patches"][0]["sha256"]
    assert result["termination"] == "max_action_value_reached"
    assert result["warnings"] or team == "team-b"


def test_import_does_not_start_process_or_load_model_or_account(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("import launched a process")
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    import companion.sim_backends.hsr_nous as adapter
    importlib.reload(adapter)
    import sys
    assert not any(key.startswith("hsr_nous") or key.startswith("langchain") for key in sys.modules)


def test_integrity_gate_rejects_modified_code_and_added_files(tmp_path):
    root = tmp_path / "core"
    root.mkdir()
    (root / "one.py").write_text("# frozen", encoding="utf-8")
    lock = {"commit": "a" * 40, "patches": [], "content_locks": [
        {"root": "repository", "path": "core", "kind": "tree", "suffixes": [".py"], "sha256": tree_digest(root)}]}
    import sys
    backend = HsrNous(python=sys.executable, repository=tmp_path, data=tmp_path, lock=lock)
    assert backend.verify()["commit"] == "a" * 40
    (root / "two.py").write_text("# unreviewed", encoding="utf-8")
    with pytest.raises(CompanionError) as caught:
        backend.verify()
    assert caught.value.code == ErrorCode.VERSION_INCOMPATIBLE


def test_unsupported_stage_is_structured_failure_and_no_web_fallback():
    backend = installed_backend()
    value = legacy_input("team-a")
    bad = BackendInput(build=value.build, stage={"stage": {"stage_template": "unimplemented"}})
    with pytest.raises(CompanionError) as caught:
        backend.compile(bad)
    assert caught.value.code == ErrorCode.UNSUPPORTED


@pytest.mark.parametrize("changes", [{"seed": True}, {"mode": "unknown"}, {"initial_sp": 6}, {"initial_energy_ratio": float("nan")}])
def test_invalid_backend_request_never_launches_process(changes, monkeypatch):
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: pytest.fail("invalid input launched process"))
    with pytest.raises(CompanionError) as caught:
        installed_backend().execute(BackendInput(build={}, stage={}, **changes))
    assert caught.value.code == ErrorCode.INVALID_INPUT
