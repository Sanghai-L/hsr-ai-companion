from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from companion.contracts import CompanionError
from companion.storage import SafeRoot, Store


def make_store(tmp_path):
    store = Store(tmp_path / "private")
    with store.transaction() as connection:
        for account in ("a", "b"):
            connection.execute("INSERT INTO accounts VALUES(?,?,?,?,?,?)", (account, account, None, None, None, "2026-11-06T00:00:00Z"))
    return store


def test_account_isolation_and_immutable_body(tmp_path):
    store = make_store(tmp_path)
    key = store.create_research("a", "研究", "仅属于 A")
    assert store.read_research("a", key) == "仅属于 A"
    with pytest.raises(CompanionError):
        store.read_research("b", key)
    assert store.latest_snapshot("b") is None


def test_concurrent_writes_and_rollback(tmp_path):
    store = make_store(tmp_path)
    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(lambda i: store.append_operation("test", {"i": i}, "a"), range(30)))
    with pytest.raises(RuntimeError):
        with store.transaction() as connection:
            connection.execute("INSERT INTO preferences VALUES('a','failed','0')")
            raise RuntimeError("rollback")
    with store.connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM operations").fetchone()[0] == 30
        assert connection.execute("SELECT COUNT(*) FROM preferences").fetchone()[0] == 0
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("INSERT INTO field_sources VALUES('b','nonexistent','x','x','{}')")


def test_real_process_crash_and_recovery(tmp_path):
    store = make_store(tmp_path)
    script = "from companion.storage import Store; import os,sys; Store(sys.argv[1]).create_research('a','断电样例','正文仍在',after_file=lambda:os._exit(23))"
    process = subprocess.run([sys.executable, "-c", script, str(store.files.root)], capture_output=True, timeout=10)
    assert process.returncode == 23, process.stderr
    reopened = Store(store.files.root)
    recovered = reopened.recover_research()
    assert len(recovered["recovered"]) == 1 and not recovered["damaged"]
    assert reopened.read_research("a", recovered["recovered"][0]) == "正文仍在"
    assert reopened.recover_research()["recovered"] == []


@pytest.mark.parametrize("path", ["../escape", "a/../../escape", "C:/outside", "a:stream", "NUL.txt", "x./f", "//server/share"])
def test_path_escape_is_rejected(tmp_path, path):
    with pytest.raises(CompanionError):
        SafeRoot(tmp_path / "data").write(path, b"x")


def test_windows_junction_escape_is_rejected(tmp_path):
    if os.name != "nt":
        pytest.skip("Windows junction acceptance is Windows-specific")
    root, outside = tmp_path / "data", tmp_path / "outside"
    safe = SafeRoot(root)
    outside.mkdir()
    junction = root / "junction"
    # Native PowerShell throughout; no shell-built deletion or cross-shell path operations.
    script = "New-Item -ItemType Junction -Path $args[0] -Target $args[1] | Out-Null"
    # -Command argument binding differs across PowerShell versions: use env for literal test paths.
    env = os.environ.copy()
    env.update(HSR_JUNCTION=str(junction), HSR_JUNCTION_TARGET=str(outside))
    script = "New-Item -ItemType Junction -Path $env:HSR_JUNCTION -Target $env:HSR_JUNCTION_TARGET | Out-Null"
    completed = subprocess.run(["powershell", "-NoProfile", "-Command", script], env=env, capture_output=True, timeout=10)
    assert completed.returncode == 0, completed.stderr
    try:
        with pytest.raises(CompanionError, match="junction"):
            safe.write("junction/escaped.txt", b"blocked")
        assert not (outside / "escaped.txt").exists()
    finally:
        junction.rmdir()  # remove the link, never recursively remove its target

