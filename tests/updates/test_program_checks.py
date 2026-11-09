from companion.updates.program import ProgramUpdates
from companion.updates.source import ReleaseSource
from companion.storage import Store
from companion.contracts import canonical


def test_program_check_only_proposes_and_does_not_download(tmp_path):
    class Source:
        def manifest(self, kind, **kwargs):
            assert kind == "program"
            return {"kind": kind, "version": "0.2.0", "sha256": "a" * 64, "size": 1, "artifact": "program.json"}
        def package(self, *args, **kwargs):
            raise AssertionError("Program detection must not download or execute code")
    store = Store(tmp_path / "personal")
    updates = ProgramUpdates(store, tmp_path / "program", source=Source())
    first = updates.check(force=True)
    second = updates.check(force=True)
    assert first.data["available"] is True and first.data["installed"] is False
    assert first.data["plan"]["id"] == second.data["plan"]["id"]
    with store.connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0] == 0


def test_offline_flag_prevents_remote_transport(tmp_path, monkeypatch):
    source = ReleaseSource("https://example.com/releases/release.json")
    def forbidden(*args, **kwargs):
        raise AssertionError("offline attempted external HTTP")
    monkeypatch.setattr("urllib.request.build_opener", forbidden)
    updates = ProgramUpdates(Store(tmp_path / "personal"), tmp_path / "app", source=source)
    result = updates.check(force=True, offline=True)
    assert result.error["code"] == "NETWORK_FAILURE"
    assert result.data["latest"] is False


def test_local_release_manifest_cannot_redirect_to_private_data(tmp_path):
    from companion.contracts import CompanionError
    import pytest
    directory = tmp_path / "source"
    directory.mkdir()
    (directory / "release.json").write_bytes(canonical({"kind": "program", "version": "0.2.0", "sha256": "a" * 64,
                                                     "size": 1, "artifact": "../personal/private.json"}))
    with pytest.raises(CompanionError):
        ReleaseSource(directory).manifest("program")

