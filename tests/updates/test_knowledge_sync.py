from concurrent.futures import ThreadPoolExecutor
import hashlib

from companion.updates.knowledge import KnowledgeSync
from .conftest import publish


def test_automatic_sync_clock_and_personal_hash(tmp_path, release):
    directory, source = release
    personal = tmp_path / "personal.sqlite3"
    personal.write_bytes(b"private bytes remain unchanged")
    before = hashlib.sha256(personal.read_bytes()).hexdigest()
    clock = [100000]
    sync = KnowledgeSync(tmp_path / "knowledge", source=source, clock=lambda: clock[0])
    assert sync.sync().data["state"] == "updated"
    publish(directory, "0.2.0")
    assert sync.sync().data["state"] == "cached"
    clock[0] += 21601
    assert sync.sync().data["version"] == "0.2.0"
    assert hashlib.sha256(personal.read_bytes()).hexdigest() == before
    assert sync.sync(force=True).data["state"] == "unchanged"


def test_corrupt_incompatible_and_offline_never_claim_latest(tmp_path, release):
    directory, source = release
    sync = KnowledgeSync(tmp_path / "knowledge", source=source)
    assert sync.sync().status == "success"
    publish(directory, "0.2.0", program_min="9.0.0", program_max="9.1.0")
    failed = sync.sync(force=True)
    assert failed.error["code"] == "VERSION_INCOMPATIBLE" and not failed.data["latest"]
    assert sync.current().manifest["version"] == "0.1.0"
    publish(directory, "0.2.0")
    (directory / "knowledge.json").write_bytes(b"corruption")
    assert sync.sync(force=True).status == "error"
    (directory / "release.json").unlink()
    assert not sync.sync(force=True).data["latest"]
    assert sync.current().manifest["version"] == "0.1.0"


def test_concurrent_sync_commits_one_valid_generation(tmp_path, release):
    _, source = release
    def run(_):
        return KnowledgeSync(tmp_path / "knowledge", source=source).sync(force=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(run, range(4)))
    assert all(r.status == "success" for r in results)
    assert [r.data["state"] for r in results].count("updated") == 1

