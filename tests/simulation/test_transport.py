import json
import subprocess
import sys

from companion.services.context import Context
from companion.services.registry import Registry
from tests.simulation.test_coverage_gate import fixture
from tests.transport.test_transport import initial, request, wire


def test_preflight_is_cli_mcp_equivalent_without_creating_player_data(tmp_path):
    data = tmp_path / "not-initialized"
    arguments = {"experiment": fixture()}
    registry = Registry(Context(data, offline=True))
    direct = registry.invoke("simulation_preflight", arguments).to_dict()
    assert direct["status"] == "partial" and registry.operations["simulation_preflight"].read_only
    cli = subprocess.run([sys.executable, "-m", "companion", "--data-dir", str(data), "--offline", "call", "simulation_preflight", "--input", "-"],
                         input=json.dumps(arguments), text=True, encoding="utf-8", capture_output=True, timeout=15)
    assert cli.returncode == 3, cli.stdout + cli.stderr
    mcp = wire(data, initial() + [request("tools/call", 3, {"name": "simulation_preflight", "arguments": arguments})])[-1]["result"]["structuredContent"]
    assert direct == json.loads(cli.stdout) == mcp
    assert not data.exists()


def test_contract_discovery_never_advertises_missing_execution_tools(tmp_path):
    registry = Registry(Context(tmp_path / "unused", offline=True))
    result = registry.invoke("simulation_schema", {})
    assert result.status == "success"
    assert registry.invoke("simulation_preflight", result.data["example_request"]).status == "partial"
    assert registry.invoke("simulation_submit", result.data["example_request"]).error["code"] == "UNSUPPORTED"


def test_account_build_import_has_no_uid_query_and_leaves_database_bytes_unchanged(tmp_path, monkeypatch):
    from companion.accounts import AccountService
    from companion.accounts.providers.enka import EnkaProvider
    from tests.simulation.test_build_import import snapshot, build, full_overrides
    context = Context(tmp_path, offline=True)
    AccountService(context.store).configure("test-account", label="synthetic", style="B")
    context.store.put_snapshot(snapshot())
    database = context.data_dir / "personal/personal.sqlite3"
    before = database.read_bytes()
    monkeypatch.setattr(EnkaProvider, "query", lambda *args: (_ for _ in ()).throw(AssertionError("unexpected UID query")))
    arguments = {"account_id": "test-account", "form_ids": [m["form_id"] for m in build()["members"]], "overrides": full_overrides()}
    registry = Registry(context)
    result = registry.invoke("simulation_build_import", arguments).to_dict()
    assert result["status"] == "success", result
    assert result["data"]["validation"]["executable"] and registry.operations["simulation_build_import"].read_only
    assert database.read_bytes() == before


def test_preflight_reports_specific_missing_inputs_through_registry(tmp_path):
    value = fixture()
    del value["parameters"]["initial_resources"]["energy_ratio"]
    result = Registry(Context(tmp_path, offline=True)).invoke("simulation_preflight", {"experiment": value})
    assert result.error["code"] == "MISSING_DATA"
    assert "initial_resources.energy_ratio" in result.missing_fields
