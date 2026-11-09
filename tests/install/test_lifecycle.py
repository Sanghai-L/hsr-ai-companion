import json
from pathlib import Path
import sqlite3

import pytest

from companion.accounts import AccountService
from companion.contracts import CompanionError, canonical
from companion.install import Installer
from companion.release.artifacts import make_artifact, digest
from companion.release.signing import test_key as new_key
from companion.storage import Store
from companion.storage.paths import file_lock


@pytest.fixture
def rig(tmp_path):
    private, public = new_key()
    data = tmp_path/"独立 玩家目录"
    store = Store(data/"personal")
    AccountService(store).configure("synthetic", style="A", region="ASIA")
    research = store.create_research("synthetic", "保留的研究", "仅用于安装故障验收")
    manager = Installer(tmp_path/"程序 中文 空格", data, trusted_keys=[public], allow_test=True,
                        health_check=lambda version, candidate: {"status": "PASS", "version": (version/"runtime/python.exe").read_text().split()[-1]})
    def package(version="0.1.3"):
        return make_artifact({"runtime/python.exe": b"synthetic "+version.encode()}, kind="program", version=version, private=private)
    return manager, package, store, research


def authorize(manager, content):
    return {"package_sha256": digest(content), "scope_path": str(manager.root)}


def test_first_repeat_upgrade_rollback_and_uninstall_preserve_personal(rig):
    manager, package, store, research = rig
    assert manager.install(package())["installed"]
    assert manager.install(package())["state"] == "unchanged"
    old = manager.state()["current"]["digest"]
    newer = package("0.1.4")
    assert manager.install(newer, authorization=authorize(manager, newer))["previous_retained"]
    assert (manager.root/"versions"/old/"runtime/python.exe").read_bytes() == b"synthetic 0.1.3"
    assert manager.rollback()["version"] == "0.1.3"
    assert store.read_research("synthetic", research) == "仅用于安装故障验收"
    assert manager.uninstall()["personal_data_preserved"]
    assert store.read_research("synthetic", research) == "仅用于安装故障验收"


def test_upgrade_requires_correct_bound_authorization_and_increasing_version(rig):
    manager, package, _, _ = rig
    manager.install(package())
    for authorization in (None, {"package_sha256": "a"*64, "scope_path": str(manager.root)},
                          {"package_sha256": digest(package("0.1.4")), "scope_path": str(manager.root.parent/"else")}):
        with pytest.raises(CompanionError):
            manager.install(package("0.1.4"), authorization=authorization)
    with pytest.raises(CompanionError):
        manager.install(package("0.1.2"), authorization=authorize(manager, package("0.1.2")))
    assert manager.state()["current"]["version"] == "0.1.3"


@pytest.mark.parametrize("failure", ["prepared", "migrated"])
def test_failed_upgrade_restores_database_and_old_pointer(rig, failure):
    manager, package, store, research = rig
    manager.install(package())
    def checkpoint(phase):
        if phase == failure:
            with store.transaction() as connection:
                connection.execute("UPDATE accounts SET style='B' WHERE id='synthetic'")
            raise OSError("injected power loss")
    manager.checkpoint = checkpoint
    newer = package("0.1.4")
    with pytest.raises(OSError):
        manager.install(newer, authorization=authorize(manager, newer))
    assert manager.state()["current"]["version"] == "0.1.3"
    assert store.require_account("synthetic")["style"] == "A"
    assert store.read_research("synthetic", research)


def test_migration_failure_and_low_space_do_not_consume_authorization(rig, monkeypatch):
    manager, package, store, _ = rig
    manager.install(package())
    newer = package("0.1.4")
    consumed = []
    auth = authorize(manager, newer) | {"consume": lambda: consumed.append(True)}
    def bad_health(*args):
        raise CompanionError(__import__('companion.contracts', fromlist=['ErrorCode']).ErrorCode.VERSION_INCOMPATIBLE, "injected schema change")
    manager.health_check = bad_health
    with pytest.raises(CompanionError):
        manager.install(newer, authorization=auth)
    assert not consumed
    monkeypatch.setattr("shutil.disk_usage", lambda root: type("Space", (), {"free": 0})())
    with pytest.raises(CompanionError):
        manager.install(newer, authorization=auth)
    assert not consumed and manager.state()["current"]["version"] == "0.1.3"


def test_occupied_activity_refuses_uninstall_but_keeps_running_version_on_upgrade(rig):
    manager, package, _, _ = rig
    manager.install(package())
    from companion.storage import SafeRoot
    with file_lock(SafeRoot(manager.root), "activity.lock", shared=True):
        with pytest.raises(CompanionError):
            manager.uninstall()
        newer = package("0.1.4")
        manager.install(newer, authorization=authorize(manager, newer))
        assert (manager.root/"versions"/digest(package())/"runtime/python.exe").exists()


def test_unmanaged_folder_and_overlapping_data_refused(tmp_path):
    existing = tmp_path/"existing"
    existing.mkdir()
    (existing/"user-file").write_text("preserve")
    manager = Installer(existing, tmp_path/"personal", trusted_keys=[])
    with pytest.raises(CompanionError):
        manager.state()
    for data in (existing, existing/"personal", tmp_path):
        with pytest.raises(CompanionError):
            Installer(existing, data, trusted_keys=[])
    assert (existing/"user-file").read_text() == "preserve"


def test_explicit_purge_is_a_separate_reversible_choice(rig):
    manager, package, store, _ = rig
    manager.install(package())
    result = manager.uninstall(purge_data=True)
    assert result["personal_data_preserved"] is False
    assert not manager.data_dir.exists()
    assert Path(result["data_quarantine"]).is_dir()


def test_modified_old_snapshot_is_refused_before_rollback_execution(rig):
    manager, package, _, _ = rig
    manager.install(package())
    newer = package("0.1.4")
    manager.install(newer, authorization=authorize(manager, newer))
    old = manager.state()["previous"]["digest"]
    (manager.root/"versions"/old/"runtime/python.exe").write_bytes(b"tampered")
    called = []
    manager.health_check = lambda *args: called.append(True)
    with pytest.raises(CompanionError):
        manager.rollback()
    assert not called and manager.state()["current"]["version"] == "0.1.4"
