import json

import pytest

from companion.accounts import AccountService
from companion.contracts import CompanionError
from companion.experiments.replay import save, replay
from companion.storage import Store
from tests.simulation.representative_cases import case


def test_changed_code_without_a_managed_snapshot_never_silently_replays(tmp_path, monkeypatch):
    store = Store(tmp_path/"personal")
    AccountService(store).configure("a", style="A")
    identifier = save(store, "a", case()).data["experiment_id"]
    monkeypatch.delenv("HSR_COMPANION_INSTALL_ROOT", raising=False)
    monkeypatch.setattr("companion.simulation.rotation.implementation_fingerprint", lambda: "0"*64)
    with pytest.raises(CompanionError) as error:
        replay(store, "a", identifier)
    assert error.value.code == "VERSION_INCOMPATIBLE"
    with store.connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM experiments").fetchone()[0] == 1
