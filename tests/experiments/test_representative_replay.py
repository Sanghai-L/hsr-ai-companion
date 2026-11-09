import json

import pytest

from companion.accounts import AccountService
from companion.contracts import CompanionError
from companion.experiments.replay import replay, save
from companion.memory.append import MemoryAppend
from companion.storage import Store
from tests.simulation.representative_cases import case


def accounts(path):
    store = Store(path)
    AccountService(store).configure("account-a", style="A")
    AccountService(store).configure("account-b", style="B")
    return store


def test_saved_input_recomputes_identically_after_real_database_reopen(tmp_path):
    store = accounts(tmp_path)
    result = save(store, "account-a", case())
    experiment_id = result.data["experiment_id"]
    reopened = Store(tmp_path, read_only=True)
    actual = replay(reopened, "account-a", experiment_id)
    assert actual.status == "success" and actual.data["same_result"] and actual.data["recomputed_from_start"]
    assert actual.data["comparison"] == result.data["comparison"]
    with pytest.raises(CompanionError):
        replay(reopened, "account-b", experiment_id)
    # The real research writer accepts the persisted experiment reference.
    memory = MemoryAppend(store).append("account-a", "conclusion", "代表性选择", "只适用于单目标假设窗口", "单目标示例偏向丹恒", topic="team",
        game_version="4.6", conditions=["单目标、E0、固定200AV假设"], experiment_ids=[experiment_id], claim_key="representative-choice")
    assert memory.status == "success"


def test_tampered_saved_input_is_not_replayed(tmp_path):
    store = accounts(tmp_path)
    experiment_id = save(store, "account-a", case()).data["experiment_id"]
    with store.transaction() as connection:
        row = connection.execute("SELECT payload FROM experiments WHERE id=?", (experiment_id,)).fetchone()
        payload = json.loads(row["payload"])
        payload["input"]["scenario"]["target_count"] = 5
        connection.execute("UPDATE experiments SET payload=? WHERE id=?", (json.dumps(payload), experiment_id))
    with pytest.raises(CompanionError) as error:
        replay(store, "account-a", experiment_id)
    assert error.value.code == "CONFLICT"


def test_program_version_change_does_not_claim_identical_method(tmp_path, monkeypatch):
    monkeypatch.delenv("HSR_COMPANION_INSTALL_ROOT", raising=False)
    import companion
    store = accounts(tmp_path)
    experiment_id = save(store, "account-a", case()).data["experiment_id"]
    monkeypatch.setattr(companion, "__version__", "9.0.0")
    with pytest.raises(CompanionError) as error:
        replay(store, "account-a", experiment_id)
    assert error.value.code == "VERSION_INCOMPATIBLE"
