"""Actual wheel in a new Windows venv; no simulator dependency in main app."""
import hashlib
import json
import os
import subprocess
import sys
import uuid
import zipfile

from companion import __version__
from record import ROOT, write_json


def main():
    target = ROOT / ".local/probes/p4" / ("干净 安装验证 " + uuid.uuid4().hex[:8])
    target.mkdir(parents=True)
    output = ROOT / ".local/evidence/D038"
    environment = os.environ.copy()
    environment.update(PYTHONUTF8="1", PYTHONIOENCODING="utf-8", TEMP=str(ROOT / ".local/tmp"), TMP=str(ROOT / ".local/tmp"),
                       UV_CACHE_DIR=str(ROOT / ".local/cache/uv"), UV_PYTHON_DOWNLOADS="never", UV_LINK_MODE="copy")
    environment.pop("PYTHONPATH", None)
    commands = []

    def run(name, args, *, expected=0, input=None, cwd=target):
        result = subprocess.run([str(arg) for arg in args], cwd=cwd, env=environment, input=input, capture_output=True,
                                text=True, encoding="utf-8", errors="replace", timeout=60,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        commands.append({"name": name, "command": [str(arg) for arg in args], "cwd": str(cwd), "exit_code": result.returncode,
                         "expected_exit_code": expected, "stdout": result.stdout, "stderr": result.stderr})
        write_json(".local/evidence/D038/fresh-install-commands.json", commands)
        if result.returncode != expected:
            raise RuntimeError(name + ": " + result.stdout[-1500:] + result.stderr[-1500:])
        return result.stdout

    run("build-wheel", [sys.executable, "-m", "hatchling", "build", "-t", "wheel", "-d", output / "dist"], cwd=ROOT)
    wheel = next((output / "dist").glob(f"hsr_ai_companion-{__version__}-*.whl"))
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        for name in ("simulator.lock.json", "coverage.json", "build-catalog.json"):
            assert "companion/resources/manifests/" + name in names
        assert "companion/resources/licenses/HSR_Nous-MIT.txt" in names
        assert not any(name.startswith((".local/", "tests/", "tools/")) for name in names)
        assert not any("MonsterConfig" in name or "team-a-run" in name for name in names)
    run("create-venv", [sys.executable, "-m", "venv", "--without-pip", target / "环境"])
    python = target / "环境/Scripts/python.exe"
    uv = ROOT / ".local/tools/uv/uv.exe"
    run("sync-locked-dependencies", [uv, "pip", "sync", "--offline", "--require-hashes", "--python", python, ROOT / "requirements.lock"])
    run("install-wheel", [uv, "pip", "install", "--offline", "--no-deps", "--python", python, wheel])
    run("verify-import-isolation", [python, "-c", "import companion,importlib.util,sys;from pathlib import Path;import companion.sim_backends.hsr_nous;from companion.modes.scenario_candidate import select_floor,resolve_character;assert str(Path(sys.prefix)) in companion.__file__;assert importlib.util.find_spec('hsr_nous') is None;assert importlib.util.find_spec('yaml') is None;print(companion.__version__)"])
    data = target / "尚未初始化 玩家资料"

    def call(operation, arguments, expected=0):
        return json.loads(run(operation, [python, "-m", "companion", "--data-dir", data, "--offline", "call", operation, "--input", "-", "--json"],
                              expected=expected, input=json.dumps(arguments, ensure_ascii=False)))

    contract = call("simulation_schema", {})
    arguments = contract["data"]["example_request"]
    expected = call("simulation_preflight", arguments, 3)
    assert not expected["data"]["complete_supported"] and not expected["data"]["game_ranking_allowed"]
    assert call("simulation_build_validate", {"build": arguments["experiment"]["parameters"]["build"]})["data"]["executable"]
    arguments["experiment"]["parameters"]["precision"] = "high"
    assert call("simulation_preflight", arguments, 3)["error"]["code"] == "UNSUPPORTED"
    assert call("simulation_submit", {}, 3)["error"]["code"] == "UNSUPPORTED"
    arguments["experiment"]["parameters"]["precision"] = "model_diagnostic"
    messages = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-11-25", "clientInfo": {"name": "p4-wheel", "version": "1"}, "capabilities": {}}},
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "simulation_preflight", "arguments": arguments}}]
    wire = run("wheel-mcp-preflight", [python, "-m", "companion", "--data-dir", data, "--offline", "mcp"],
               input="\n".join(json.dumps(m) for m in messages) + "\n")
    actual = json.loads(wire.splitlines()[-1])["result"]["structuredContent"]
    assert actual == expected
    damage = call("calculation_schema", {"kind": "damage"})
    assert call("calculate", damage["data"]["example_request"])["data"]["result"]["value"] == 2025
    assert not data.exists(), "read-only tools initialized player data"
    write_json(".local/evidence/D038/fresh-install-summary.json", {"status": "PASS", "commands": len(commands), "failed": 0,
        "wheel": str(wheel), "wheel_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(), "target": str(target),
        "uid_queries": 0, "core_installed_in_main_runtime": False, "scope": "partial-P4 contracts/build/preflight; not Alpha or full-scene acceptance"})
    print(json.dumps({"status": "PASS", "commands": len(commands), "target": str(target)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
