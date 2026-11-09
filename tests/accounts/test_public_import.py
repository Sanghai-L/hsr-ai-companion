import copy
import json
from pathlib import Path

import pytest

from companion.accounts import AccountService
from companion.accounts.providers.enka import EnkaProvider
from companion.accounts.refresh import AccountRefresh
from companion.contracts import CompanionError, canonical
from companion.services.context import Context
from companion.services.registry import Registry
from companion.sources.http import Response
from companion.storage import Store

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/uid"


def fixture(name):
    return json.loads((FIXTURES / (name + ".json")).read_bytes())


@pytest.fixture
def rig(tmp_path):
    store = Store(tmp_path)
    accounts = AccountService(store)
    accounts.configure("a", uid="100000001", region="ASIA")
    accounts.configure("b", uid="100000002", region="ASIA")
    response, calls, clock = [fixture("partial")], [], [1000.0]
    def transport(url):
        calls.append(url)
        value = response[0]
        if isinstance(value, BaseException):
            raise value
        return Response(value["http_status"], canonical(value["body"]), value.get("headers", {}))
    service = AccountRefresh(store, provider=EnkaProvider(transport=transport), clock=lambda: clock[0])
    return store, accounts, service, response, calls, clock


def test_import_ttl_manual_override_missing_and_account_isolation(rig):
    store, accounts, service, response, calls, clock = rig
    first = service.refresh("a", "user:explicit import", "import")
    assert first.data["uid_refreshed"] and first.data["showcase_count"] == 1 and len(calls) == 1
    snapshot = store.latest_snapshot("a")
    assert snapshot["versions"]["game"] is None and snapshot["roster_completeness"] == "partial"
    level = next(f for f in snapshot["fields"] if f["field_id"] == "level" and f["entity_id"].startswith("character:"))
    manual = copy.deepcopy(level)
    manual["quantity"]["value"] = 70
    manual["source"]["type"] = "manual"
    manual["source"]["ref"] = "user:manual correction"
    accounts.manual_update("a", [manual], expected_snapshot_id=snapshot["snapshot_id"])
    service.refresh("a", "user:refresh within TTL", "refresh")
    assert len(calls) == 1
    clock[0] += 61
    changed = service.refresh("a", "user:new explicit refresh", "refresh")
    assert changed.data["manual_conflicts"] and len(calls) == 2
    response[0] = fixture("missing-field")
    clock[0] += 61
    service.refresh("a", "user:missing", "refresh")
    kept = store.latest_snapshot("a")
    assert any(f["quantity"]["value"] == 70 for f in kept["fields"])
    assert store.latest_snapshot("b") is None
    response[0] = fixture("empty")
    clock[0] += 61
    empty = service.refresh("a", "user:empty", "refresh")
    assert empty.data["showcase_count"] == 0
    assert store.latest_snapshot("a")["characters"][0]["ownership"] == "owned"
    assert accounts.get("a")["uid_import"] == "imported_public_partial"
    assert accounts.changes("a", changed.data["query_id"])["items"]


@pytest.mark.parametrize("name", ["invalid-uid", "not-found", "maintenance", "rate-limit", "schema-change"])
def test_remote_failure_never_overwrites_good_snapshot(rig, name):
    store, accounts, service, response, calls, clock = rig
    service.refresh("a", "user:import", "import")
    before = store.latest_snapshot("a")
    clock[0] += 61
    response[0] = fixture(name)
    with pytest.raises(CompanionError):
        service.refresh("a", "user:failure", "refresh")
    assert store.latest_snapshot("a") == before
    assert len(calls) == 2  # exactly one attempt, no fallback or retry


def test_unknown_fields_stay_unknown_and_no_synthetic_panel(rig):
    store, _, service, response, _, _ = rig
    response[0] = fixture("missing-field")
    result = service.refresh("a", "user:import missing", "import")
    fields = store.latest_snapshot("a")["fields"]
    assert all(f["quantity"]["state"] == "unknown" and f["quantity"]["value"] is None for f in fields)
    assert result.missing_fields and all(f["basis"] == "record" for f in fields)


def test_explicit_authorization_and_offline_enforced(rig):
    store, _, service, _, calls, _ = rig
    with pytest.raises(CompanionError):
        service.refresh("a", "", "refresh")
    with pytest.raises(CompanionError):
        AccountRefresh(store, offline=True).refresh("a", "user:import", "import")
    assert calls == []


def test_timeout_does_not_write_empty_account(rig):
    store, _, service, response, _, _ = rig
    from companion.contracts import ErrorCode
    response[0] = CompanionError(ErrorCode.NETWORK_FAILURE, "timeout", retryable=True)
    with pytest.raises(CompanionError):
        service.refresh("a", "user:import", "import")
    assert store.latest_snapshot("a") is None


def test_stale_manual_patch_and_read_paths_never_refresh(tmp_path, monkeypatch):
    context = Context(tmp_path, offline=True)
    accounts = AccountService(context.store)
    accounts.configure("a", uid="100000001", region="ASIA", style="A")
    def no_query(*args, **kwargs):
        pytest.fail("local read or bootstrap must never query UID")
    monkeypatch.setattr(EnkaProvider, "query", no_query)
    registry = Registry(context)
    for name in ["session_bootstrap", "account_get", "status", "updates_check"]:
        registry.invoke(name, {})
    valid = {"entity_id": "account", "field_id": "stellar_jade", "quantity": {"value": 1, "unit": "count", "state": "known", "precision": None},
             "source": {"type": "manual", "ref": "user:test", "observed_at": "2026-11-08T00:00:00Z"}, "confirmed": True, "basis": "record"}
    assert registry.invoke("account_patch", {"account_id": "a", "expected_snapshot_id": "stale", "fields": [valid]}).error["code"] == "CONFLICT"


def test_concurrent_manual_write_during_remote_fetch_is_not_lost(rig):
    store, accounts, service, response, calls, clock = rig
    service.refresh("a", "user:initial", "import")
    clock[0] += 61
    base_query = service.provider.query
    def concurrent(uid):
        old = store.latest_snapshot("a")
        field = copy.deepcopy(old["fields"][0])
        field["source"]["type"] = "manual"
        field["source"]["ref"] = "user:concurrent"
        field["quantity"]["value"] = 65
        accounts.manual_update("a", [field])
        return base_query(uid)
    service.provider.query = concurrent
    with pytest.raises(CompanionError) as error:
        service.refresh("a", "user:refresh", "refresh")
    assert error.value.code == "CONFLICT"
    assert store.latest_snapshot("a")["fields"][0]["quantity"]["value"] == 65
