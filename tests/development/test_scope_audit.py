"""Protect approved scope changes and retained historical evidence."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("p4_scope_audit_checks", ROOT / "tools/p4/scope_audit.py")
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


def write(root, name, value):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False) if isinstance(value, dict) else value, encoding="utf-8")


def fixture(root):
    write(root, "prd.md", "original PRD")
    write(root, "plan.md", "approved simplified scope")
    write(root, "decision.md", "explicit user scope change")
    baseline = {"prd": "prd.md", "sha256": audit.digest(root / "prd.md"),
                "planning_hashes": {"plan.md": hashlib.sha256(b"old full simulation scope").hexdigest()},
                "current_scope_decision": "decision.md",
                "planning_revisions": [{"id": "explicit-scope-revision", "decision": "decision.md",
                                         "planning_hashes": {"plan.md": audit.digest(root / "plan.md")}}]}
    write(root, "docs/requirements/baseline.json", baseline)
    return baseline


def test_approved_revision_passes_without_rewriting_historical_hashes(tmp_path):
    baseline = fixture(tmp_path)
    before = (tmp_path / "docs/requirements/baseline.json").read_bytes()
    report = audit.check_planning_baseline(tmp_path)
    assert report["current_files_match_approved_revision"] and not report["current_files_match_original"]
    assert report["historical_hashes"] == baseline["planning_hashes"]
    assert (tmp_path / "docs/requirements/baseline.json").read_bytes() == before


@pytest.mark.parametrize("file,content,message", [("plan.md", "unapproved edit", "approved planning checksum mismatch"),
                                                   ("prd.md", "rewritten PRD", "original PRD checksum mismatch")])
def test_unapproved_plan_or_prd_edits_still_fail(tmp_path, file, content, message):
    fixture(tmp_path)
    write(tmp_path, file, content)
    with pytest.raises(ValueError, match=message):
        audit.check_planning_baseline(tmp_path)


def test_missing_scope_decision_is_not_an_approved_revision(tmp_path):
    fixture(tmp_path)
    (tmp_path / "decision.md").unlink()
    with pytest.raises(ValueError, match="decision is missing"):
        audit.check_planning_baseline(tmp_path)


def test_historical_baseline_without_revision_remains_strict(tmp_path):
    value = fixture(tmp_path)
    value.pop("planning_revisions")
    value.pop("current_scope_decision")
    write(tmp_path, "docs/requirements/baseline.json", value)
    with pytest.raises(ValueError, match="approved planning checksum mismatch"):
        audit.check_planning_baseline(tmp_path)


def test_scope_guard_prevents_real_old_finalizer_from_resetting_records(tmp_path):
    fixture(tmp_path)
    for name in ("finalize.py", "record.py", "scope_audit.py"):
        target = tmp_path / "tools/p4" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / "tools/p4" / name, target)
    write(tmp_path, "docs/development/task-status.json", {"tasks": [{"id": "D038", "status": "IN_PROGRESS"}]})
    write(tmp_path, "docs/gates/P4-alpha.json", {"status": "NOT_PASSED_SIMPLIFIED_SCOPE_PENDING"})
    tracked = [tmp_path / "docs/development/task-status.json", tmp_path / "docs/gates/P4-alpha.json"]
    before = [path.read_bytes() for path in tracked]
    result = subprocess.run([sys.executable, "-X", "utf8", str(tmp_path / "tools/p4/finalize.py")], cwd=tmp_path,
                            capture_output=True, text=True, encoding="utf-8", timeout=15)
    assert result.returncode != 0 and "未写入记录" in result.stderr
    assert [path.read_bytes() for path in tracked] == before
    assert not (tmp_path / ".local").exists()
