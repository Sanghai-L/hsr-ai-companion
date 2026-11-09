import json
import subprocess
import sys

import pytest

from companion.accounts.providers.enka import EnkaProvider
from companion.services.context import Context
from companion.services.registry import Registry
from tests.simulation.representative_cases import case
from tests.transport.test_transport import initial, request, wire


@pytest.mark.parametrize("mode,short", [("memory_of_chaos", "moc"), ("pure_fiction", "pf"), ("apocalyptic_shadow", "as"), ("anomaly_arbitration", "aa")])
def test_four_modes_cli_mcp_equal_and_do_not_touch_accounts_or_uid(mode, short, tmp_path, monkeypatch):
    data = tmp_path / "not-created"
    monkeypatch.setattr(EnkaProvider, "query", lambda *a: (_ for _ in ()).throw(AssertionError("unexpected UID")))
    arguments = {"mode": mode, "request": case(short)}
    registry = Registry(Context(data, offline=True))
    direct = registry.invoke("mode_analyze", arguments)
    assert direct.status == "success", direct.to_dict()
    process = subprocess.run([sys.executable, "-X", "utf8", "-m", "companion", "--data-dir", str(data), "--offline", "call", "mode_analyze", "--input", "-"],
        input=json.dumps(arguments), text=True, encoding="utf-8", capture_output=True, timeout=15)
    assert process.returncode == 0, process.stdout + process.stderr
    mcp = wire(data, initial() + [request("tools/call", 3, {"name": "mode_analyze", "arguments": arguments})])[-1]["result"]["structuredContent"]
    assert direct.data == json.loads(process.stdout)["data"] == mcp["data"]
    assert not data.exists()


def test_contract_discovery_and_real_mode_routing_through_registry(tmp_path):
    registry = Registry(Context(tmp_path / "unused", offline=True))
    for query, mode in [("混沌回忆配队", "memory_of_chaos"), ("虚构叙事怎么打", "pure_fiction"), ("末日幻影打不破", "apocalyptic_shadow"), ("异相仲裁三队", "anomaly_arbitration")]:
        chosen = registry.invoke("mode_select", {"query": query})
        assert chosen.data["selected_mode"] == mode
        schema = registry.invoke("analysis_schema", {"mode": mode})
        assert schema.status == "success"
        assert registry.invoke("simulation_compare", schema.data["example_request"]).status == "success"
        assert registry.invoke("mode_analyze", {"mode": mode}).status == "partial"
    assert not (tmp_path / "unused").exists()
