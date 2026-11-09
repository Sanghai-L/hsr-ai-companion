import json
import subprocess
import sys

import pytest

from companion.contracts import canonical
from companion.services.context import Context
from companion.services.registry import Registry
from tests.experiments.helpers import fixture
from tests.transport.test_transport import initial, request, wire


@pytest.mark.parametrize("name,operation", [("damage","calculate"),("timeline","calculate"),("gacha","calculate"),("pull-plan","plan_pulls")])
def test_quantitative_tools_are_read_only_cli_mcp_equivalent_and_do_not_initialize_uid(name, operation, tmp_path):
    data = tmp_path / "nonexistent-player"
    arguments = {"experiment": fixture(name)}
    registry = Registry(Context(data, offline=True))
    direct = registry.invoke(operation, arguments).to_dict()
    assert direct["status"] == "success", direct
    assert registry.operations[operation].read_only
    cli = subprocess.run([sys.executable,"-m","companion","--data-dir",str(data),"--offline","call",operation,"--input","-"],
        input=json.dumps(arguments,ensure_ascii=False),text=True,encoding="utf-8",capture_output=True,timeout=15)
    assert cli.returncode == 0, cli.stdout + cli.stderr
    mcp = wire(data, initial()+[request("tools/call",3,{"name":operation,"arguments":arguments})])[-1]["result"]["structuredContent"]
    assert direct["data"] == json.loads(cli.stdout)["data"] == mcp["data"]
    assert direct["versions"] == mcp["versions"] and direct["warnings"] == mcp["warnings"]
    assert not data.exists()


def test_schema_is_self_contained_and_missing_inputs_are_specific(tmp_path):
    registry = Registry(Context(tmp_path,offline=True))
    schema = registry.operations["calculate"].schema
    assert all("$ref" not in canonical(v).decode() for v in schema["properties"]["experiment"]["oneOf"])
    arguments = {"experiment":fixture("damage")}
    del arguments["experiment"]["parameters"]["crit_rate"]
    missing = registry.invoke("calculate",arguments).to_dict()
    assert missing["error"]["code"] == "MISSING_DATA" and "crit_rate" in missing["missing_fields"]
    arguments["experiment"]["parameters"]["crit_rate"] = .5
    arguments["experiment"]["parameters"]["arbitrary_executable"] = "not allowed"
    assert registry.invoke("calculate",arguments).error["code"] == "INVALID_INPUT"


def test_declared_cross_version_comparison_does_not_produce_ranking(tmp_path):
    left, right = fixture("damage"),fixture("damage")
    right["conditions"]["game_version"] = "4.7"
    registry = Registry(Context(tmp_path,offline=True))
    assert registry.invoke("experiment_compare",{"left":left,"right":right}).error["code"] == "VERSION_INCOMPATIBLE"
    result = registry.invoke("experiment_compare",{"left":left,"right":right,"declaration":"明确跨版本情景"}).to_dict()
    assert result["status"] == "success" and result["data"]["ranking_permitted"] is False


@pytest.mark.parametrize("kind,operation", [("damage","calculate"),("timeline","calculate"),("gacha","calculate"),("pull_plan","plan_pulls")])
def test_contract_discovery_example_works_without_reading_development_tree(kind, operation, tmp_path):
    registry = Registry(Context(tmp_path/"not-initialized",offline=True))
    result = registry.invoke("calculation_schema",{"kind":kind}).to_dict()
    assert result["status"] == "success" and registry.operations["calculation_schema"].read_only
    sample = result["data"]["example_request"]
    assert registry.invoke(operation,sample).status == "success"
    assert not (tmp_path/"not-initialized").exists()
