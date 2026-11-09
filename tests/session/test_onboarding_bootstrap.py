import json
import subprocess
import sys

from companion.accounts import AccountService
from companion.contracts import canonical
from companion.services.context import Context
from companion.services.registry import Registry
from companion.session import bootstrap


def field(value, state="known"):
    return {"entity_id": "account", "field_id": "stellar_jade", "quantity": {
        "value": value, "unit": "count", "state": state, "precision": None},
        "source": {"type": "synthetic", "ref": "original-offline-test", "observed_at": "2026-11-06T00:00:00Z"},
        "confirmed": True, "basis": "record"}


def test_first_session_asks_style_without_default_and_no_uid_network(tmp_path):
    context = Context(tmp_path, offline=True)
    first = bootstrap(context)
    assert first.missing_fields == ["account", "style"]
    assert first.data["state"]["style"] is None and first.data["uid_refreshed"] is False
    assert first.data["updates"]["knowledge"]["data"]["latest"] is False
    assert [option["value"] for option in first.data["questions"][-1]["options"]] == ["A", "B"]


def test_dual_accounts_style_changes_and_manual_unknowns(tmp_path):
    context = Context(tmp_path, offline=True)
    accounts = AccountService(context.store)
    accounts.configure("a", label="合成账号 A", style="A")
    accounts.configure("b", label="合成账号 B", style="B")
    accounts.manual_update("a", [field(0)])
    accounts.manual_update("b", [field(None, "unknown")])
    accounts.select("b")
    assert context.inspect()["style"] == "B"
    assert accounts.get()["snapshot"]["fields"][0]["quantity"]["value"] is None
    assert accounts.get("a")["snapshot"]["fields"][0]["quantity"]["value"] == 0
    accounts.configure("b", style="A")
    assert context.inspect()["style"] == "A"
    assert accounts.get("a")["account"]["style"] == "A"
    assert bootstrap(context).missing_fields == ["uid", "region"]


def test_restart_real_process_and_manual_continuation(tmp_path):
    context = Context(tmp_path, offline=True)
    accounts = AccountService(context.store)
    accounts.configure("a", style="B")
    accounts.manual_update("a", [field(123)])
    command = [sys.executable, "-m", "companion", "--data-dir", str(tmp_path), "--offline", "call", "session_bootstrap", "--input", "-", "--json"]
    process = subprocess.run(command, input="{}", capture_output=True, text=True, encoding="utf-8", timeout=10)
    assert process.returncode == 3
    restarted = json.loads(process.stdout)
    assert restarted["data"]["state"]["default_account_id"] == "a"
    assert restarted["data"]["state"]["style"] == "B"
    assert restarted["data"]["uid_refreshed"] is False
    assert AccountService(Context(tmp_path).store).get()["snapshot"]["fields"][0]["quantity"]["value"] == 123


def test_bad_manual_update_does_not_overwrite_previous_snapshot(tmp_path):
    registry = Registry(Context(tmp_path, offline=True))
    registry.invoke("account_configure", {"account_id": "a"})
    registry.invoke("account_manual_update", {"account_id": "a", "fields": [field(10)]})
    before = registry.invoke("account_get", {"account_id": "a"}).data["snapshot"]
    invalid = field(0, "unknown")
    failure = registry.invoke("account_manual_update", {"account_id": "a", "fields": [invalid]})
    assert failure.status == "error"
    assert registry.invoke("account_get", {"account_id": "a"}).data["snapshot"] == before
    # P2 implements this operation, but an account ID alone never authorizes a query.
    assert registry.invoke("account_refresh", {"account_id": "a"}).error["code"] == "INVALID_INPUT"


def test_read_only_account_tools_do_not_initialize_or_modify_data(tmp_path):
    directory = tmp_path / "new"
    registry = Registry(Context(directory, offline=True))
    assert registry.invoke("account_list", {}).data["accounts"] == []
    assert registry.invoke("account_get", {}).error["code"] == "MISSING_DATA"
    assert not directory.exists()
    registry.invoke("account_configure", {"account_id": "a"})
    import hashlib
    path = directory / "personal/personal.sqlite3"
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    assert registry.invoke("account_get", {}).status == "success"
    assert registry.invoke("account_list", {}).status == "success"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_account_fields_page_without_mutation_failure(tmp_path):
    registry = Registry(Context(tmp_path, offline=True))
    registry.invoke("account_configure", {"account_id": "a"})
    fields = []
    for index in range(14):
        item = field(index)
        item["field_id"] = f"resource_{index}"
        item["source"]["ref"] = "x" * 8000
        fields.append(item)
    saved = registry.invoke("account_manual_update", {"account_id": "a", "fields": fields})
    assert saved.status == "success" and saved.data["field_count"] == 14
    found, cursor = [], None
    while True:
        page = registry.invoke("account_get", {"account_id": "a", "cursor": cursor, "page_size": 20})
        assert page.status == "success"
        found += [f["field_id"] for f in page.data["snapshot"]["fields"]]
        cursor = page.data["next_cursor"]
        if cursor is None:
            break
    assert len(found) == len(set(found)) == 14

