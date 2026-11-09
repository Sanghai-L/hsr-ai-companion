from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from companion.accounts import AccountService
from companion.contracts import CompanionError, ErrorCode, canonical
from companion.install import Installer
from companion.release.artifacts import digest, make_artifact
from companion.release.signing import test_key as new_key
from companion.services.context import Context
from companion.services.registry import Registry
from companion.storage import Store


def test_actual_process_death_recovers_staged_program_and_database(tmp_path):
    private, public = new_key()
    root, data = tmp_path/"app", tmp_path/"player"
    store = Store(data/"personal")
    AccountService(store).configure("synthetic", style="A", region="ASIA")
    def package(version):
        return make_artifact({"runtime/python.exe": version.encode()}, kind="program", version=version, private=private)
    health = lambda version, candidate: {"status": "PASS", "version": (version/"runtime/python.exe").read_text()}
    manager = Installer(root, data, trusted_keys=[public], allow_test=True, health_check=health)
    manager.install(package("0.1.3"))
    (tmp_path/"next.json").write_bytes(package("0.1.4"))
    (tmp_path/"trust.json").write_bytes(canonical({"schema_version": 1, "keys": [public]}))
    code = """
import os,sys
from pathlib import Path
from companion.install import Installer
from companion.release.artifacts import digest
from companion.release.signing import load_trust
from companion.storage import Store
base=Path(sys.argv[1]); content=(base/'next.json').read_bytes()
def checkpoint(phase):
    if phase=='migrated':
        with Store(base/'player/personal').transaction() as connection:
            connection.execute("UPDATE accounts SET style='B' WHERE id='synthetic'")
        os._exit(91)
manager=Installer(base/'app',base/'player',trusted_keys=load_trust(base/'trust.json'),allow_test=True,
    health_check=lambda version,candidate:{'status':'PASS','version':(version/'runtime/python.exe').read_text()},checkpoint=checkpoint)
manager.install(content,authorization={'package_sha256':digest(content),'scope_path':str(base/'app')})
"""
    child = subprocess.run([sys.executable, "-c", code, str(tmp_path)], capture_output=True, timeout=20)
    assert child.returncode == 91, child.stderr
    assert manager.recover()["recovered"]
    assert manager.state()["current"]["version"] == "0.1.3"
    assert store.require_account("synthetic")["style"] == "A"
    assert not manager.recover()["recovered"]


def test_concurrent_actual_sessions_preserve_account_partition_and_all_writes(tmp_path):
    store = Store(tmp_path/"personal")
    for account in ("a", "b"):
        AccountService(store).configure(account, style="A")
    code = """
import sys
from companion.storage import Store
s=Store(sys.argv[1])
for index in range(8):
    s.create_research(sys.argv[2],sys.argv[3]+str(index),'synthetic concurrency body')
"""
    children = [subprocess.Popen([sys.executable, "-c", code, str(store.files.root), account, str(index)],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
                for index, account in enumerate(("a", "b", "a", "b"))]
    for child in children:
        _, stderr = child.communicate(timeout=30)
        assert child.returncode == 0, stderr
    with store.connection() as connection:
        assert dict(connection.execute("SELECT account_id,COUNT(*) FROM research GROUP BY account_id")) == {"a": 16, "b": 16}
    assert store.recover_research() == {"recovered": [], "damaged": [], "missing": []}


@pytest.mark.parametrize("behavior,expected", [("crash", ErrorCode.INTERNAL_FAILURE), ("timeout", ErrorCode.BUDGET_EXHAUSTED)])
def test_real_worker_crash_and_timeout_are_reaped(tmp_path, monkeypatch, behavior, expected):
    from companion.sim_backends.hsr_nous import HsrNous
    from companion.sim_backends.base import BackendInput
    backend = HsrNous(python=sys.executable, repository=tmp_path, data=tmp_path)
    monkeypatch.setattr(backend, "verify", lambda: {})
    original_run, original_popen = subprocess.run, subprocess.Popen
    created = []
    def popen(*args, **kwargs):
        child = original_popen(*args, **kwargs)
        created.append(child)
        return child
    def run(command, **kwargs):
        code = "import os;os._exit(37)" if behavior == "crash" else "import time;time.sleep(30)"
        return original_run([sys.executable, "-c", code], **kwargs)
    monkeypatch.setattr(subprocess, "Popen", popen)
    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(CompanionError) as error:
        backend.execute(BackendInput(build={}, stage={}), timeout=.2)
    assert error.value.code == expected
    assert len(created) == 1 and created[0].poll() is not None


def test_mcp_disconnect_exits_without_leaving_an_application_worker(tmp_path):
    request = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-11-25"}}
    child = subprocess.run([sys.executable, "-m", "companion", "--data-dir", str(tmp_path/"unused"), "--offline", "mcp"],
                           input=canonical(request)+b"\n", capture_output=True, timeout=10)
    assert child.returncode == 0 and json.loads(child.stdout)["result"]["serverInfo"]
    assert not (tmp_path/"unused").exists()


def test_shared_file_lock_supports_an_actual_second_process_reader(tmp_path):
    from companion.storage import SafeRoot
    from companion.storage.paths import file_lock
    root = SafeRoot(tmp_path)
    code = "from companion.storage import SafeRoot; from companion.storage.paths import file_lock; import sys; r=SafeRoot(sys.argv[1]); lock=file_lock(r,'shared.lock',shared=True,timeout=.5); lock.__enter__(); lock.__exit__(None,None,None)"
    with file_lock(root, "shared.lock", shared=True):
        child = subprocess.run([sys.executable, "-c", code, str(tmp_path)], capture_output=True, timeout=5)
        assert child.returncode == 0, child.stderr


def test_disk_write_failure_keeps_existing_research(tmp_path, monkeypatch):
    store = Store(tmp_path/"personal")
    AccountService(store).configure("a", style="A")
    prior = store.create_research("a", "existing", "preserve this")
    original = store.files.write
    def full(relative, *args, **kwargs):
        if str(relative).startswith("research/"):
            raise OSError(28, "injected disk full")
        return original(relative, *args, **kwargs)
    monkeypatch.setattr(store.files, "write", full)
    with pytest.raises(OSError):
        store.create_research("a", "new", "should not commit")
    assert store.read_research("a", prior) == "preserve this"
    with store.connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM research").fetchone()[0] == 1


def test_corrupt_database_cli_returns_sanitized_error_without_traceback(tmp_path):
    personal = tmp_path/"personal"
    personal.mkdir()
    (personal/"personal.sqlite3").write_bytes(b"SECRET_CORRUPT_SQLITE_BODY")
    private, public = new_key()
    artifact = tmp_path/"candidate.TEST.json"
    artifact.write_bytes(make_artifact({"runtime/python.exe": b"never executed"}, kind="program", version="0.1.3", private=private))
    trust = tmp_path/"trust.json"
    trust.write_bytes(canonical({"schema_version": 1, "keys": [public]}))
    child = subprocess.run([sys.executable, "-m", "companion", "--data-dir", str(tmp_path), "install-program",
                            "--root", str(tmp_path.parent/(tmp_path.name+"-app")), "--trust", str(trust), "--package", str(artifact), "--allow-test"], capture_output=True, timeout=10)
    value = json.loads(child.stdout)
    assert child.returncode == 4 and value["error"]["code"] == "INTERNAL_FAILURE"
    assert not child.stderr and b"SECRET_CORRUPT_SQLITE_BODY" not in child.stdout
