import subprocess
import sys

from companion.updates.knowledge import KnowledgeSync
from .conftest import publish


def test_real_crash_before_pointer_commit_retains_old_package(tmp_path, release):
    directory, source = release
    target = tmp_path / "knowledge"
    sync = KnowledgeSync(target, source=source)
    assert sync.sync().status == "success"
    publish(directory, "0.2.0")
    script = ("from companion.updates.knowledge import KnowledgeSync; from companion.updates.source import ReleaseSource; "
              "import os,sys; KnowledgeSync(sys.argv[1],source=ReleaseSource(sys.argv[2])).sync(force=True,checkpoint=lambda _:os._exit(29))")
    process = subprocess.run([sys.executable, "-c", script, str(target), str(directory)], capture_output=True, timeout=10)
    assert process.returncode == 29, process.stderr
    assert sync.current().manifest["version"] == "0.1.0"
    assert sync.sync(force=True).data["version"] == "0.2.0"


def test_damaged_current_generation_recovers_previous(tmp_path, release):
    directory, source = release
    sync = KnowledgeSync(tmp_path / "knowledge", source=source)
    sync.sync()
    publish(directory, "0.2.0")
    sync.sync(force=True)
    current = sync.current()
    sync.files.path(f"packages/{current.fingerprint}/index.json").write_bytes(b"[]")
    assert sync.recover() == {"version": "0.1.0", "recovered": True}
    assert sync.current().manifest["version"] == "0.1.0"

