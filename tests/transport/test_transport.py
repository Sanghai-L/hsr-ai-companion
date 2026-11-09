import io
import json
import subprocess
import sys

from companion.contracts import ToolResult
from companion.mcp_server import serve
from companion.services.context import Context
from companion.services.registry import Registry, input_schema


def request(method, id=None, params=None):
    return {"jsonrpc": "2.0", "method": method, **({"id": id} if id is not None else {}),
            **({"params": params} if params is not None else {})}


def initial():
    return [request("initialize", 1, {"protocolVersion": "2025-11-25", "capabilities": {},
        "clientInfo": {"name": "offline-test", "version": "1"}}), request("notifications/initialized")]


def wire(data_dir, messages):
    process = subprocess.run([sys.executable, "-m", "companion", "--data-dir", str(data_dir), "--offline", "mcp"],
        input="\n".join(m if isinstance(m, str) else json.dumps(m, ensure_ascii=False) for m in messages) + "\n",
        text=True, encoding="utf-8", capture_output=True, timeout=10)
    assert process.returncode == 0 and process.stderr == "", process.stderr
    return [json.loads(line) for line in process.stdout.splitlines()]


def test_cli_mcp_parity_and_read_only_doctor(tmp_path):
    directory = tmp_path / "data"
    cli = subprocess.run([sys.executable, "-m", "companion", "--data-dir", str(directory), "--offline", "status", "--json"],
                         capture_output=True, text=True, encoding="utf-8", timeout=10)
    mcp = wire(directory, initial() + [request("tools/call", 3, {"name": "status", "arguments": {}})])
    assert cli.returncode == 0
    assert json.loads(cli.stdout) == mcp[-1]["result"]["structuredContent"]
    assert not directory.exists()
    assert Registry(Context(directory, offline=True)).invoke("doctor", {}).status == "success"
    assert not directory.exists()


def test_handshake_bad_params_unknown_and_eof_restart(tmp_path):
    result = wire(tmp_path, [request("tools/list", 0), request("notifications/initialized")] + initial() + [
        request("tools/call", 2, {"name": "status", "arguments": {"uid": "not-allowed"}}),
        request("tools/call", 3, {"name": "simulation_submit", "arguments": {}}),
        request("unknown", 4), request("ping", 5), "broken{", "[]"])
    assert result[0]["error"]["code"] == -32002
    assert result[2]["result"]["isError"]
    assert result[2]["result"]["structuredContent"]["error"]["code"] == "INVALID_INPUT"
    assert result[3]["result"]["structuredContent"]["error"]["code"] == "UNSUPPORTED"
    assert result[4]["error"]["code"] == -32601
    assert result[-2]["error"]["code"] == -32700
    assert result[-1]["error"]["code"] == -32600
    assert wire(tmp_path, initial() + [request("ping", 6)])[-1]["result"] == {}


def test_pagination_and_output_limit(tmp_path):
    registry = Registry(Context(tmp_path, offline=True))
    first = registry.invoke("capabilities", {"page_size": 2}).data
    second = registry.invoke("capabilities", {"page_size": 2, "cursor": first["next_cursor"]}).data
    assert not {i["name"] for i in first["items"]} & {i["name"] for i in second["items"]}
    assert registry.invoke("capabilities", {"cursor": "bad"}).error["code"] == "INVALID_INPUT"
    registry.add("huge", "test", input_schema(), lambda: ToolResult(data="x" * 65536), True)
    assert registry.invoke("huge", {}).error["code"] == "BUDGET_EXHAUSTED"
    listed = wire(tmp_path, initial() + [request("tools/list", 3, {"_meta": {"progressToken": "host-trace"}})])[-1]["result"]
    assert len(listed["tools"]) == 5 and listed["nextCursor"]


def test_duplicate_ids_cannot_repeat_mutation(tmp_path):
    registry = Registry(Context(tmp_path, offline=True))
    mutations = []
    registry.add("mutate", "test", input_schema(), lambda: (mutations.append(1) or ToolResult(data=len(mutations))))
    command = request("tools/call", 2, {"name": "mutate", "arguments": {}})
    messages = initial() + [command, command, request("tools/call", 2, {"name": "doctor"})]
    stdout = io.StringIO()
    serve(registry, io.StringIO("\n".join(json.dumps(m) for m in messages)), stdout)
    replies = [json.loads(line) for line in stdout.getvalue().splitlines()]
    assert len(mutations) == 1 and replies[1] == replies[2]
    assert replies[-1]["error"]["code"] == -32600


def test_invalid_cli_input_and_noninteractive_consent(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("[]")
    result = subprocess.run([sys.executable, "-m", "companion", "--data-dir", str(tmp_path), "--offline",
        "call", "status", "--input", str(path), "--json"], capture_output=True, text=True, encoding="utf-8", timeout=10)
    assert result.returncode == 2
    assert json.loads(result.stdout)["error"]["code"] == "INVALID_INPUT"

