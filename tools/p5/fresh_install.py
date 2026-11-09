"""Offline wheel installation in a new Chinese-space venv, no host/model calls."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[2]


def main():
    label = uuid.uuid4().hex[:10]
    evidence = ROOT / ".local/evidence/D049" / ("fresh-" + label)
    target = ROOT / ".local/probes/p5" / ("干净 安装 " + label)
    evidence.mkdir(parents=True)
    target.mkdir(parents=True)
    environment = os.environ.copy()
    environment.update(PYTHONUTF8="1", PYTHONIOENCODING="utf-8", TEMP=str(target), TMP=str(target),
                       UV_CACHE_DIR=str(ROOT/".local/cache/uv"), UV_PYTHON_DOWNLOADS="never", UV_LINK_MODE="copy")
    environment.pop("PYTHONPATH", None)
    records = []

    def run(name, command, *, expected=0, input=None, cwd=target):
        result = subprocess.run([str(item) for item in command], input=input, cwd=cwd, env=environment,
                                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
        records.append({"name": name, "command": [str(item) for item in command], "cwd": str(cwd),
                        "exit_code": result.returncode, "expected_exit_code": expected,
                        "stdout": result.stdout, "stderr": result.stderr})
        (evidence/"commands.json").write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
        if result.returncode != expected:
            raise RuntimeError(name + ": " + result.stdout[-1800:] + result.stderr[-1800:])
        return result.stdout

    run("build-wheel", [sys.executable, "-m", "hatchling", "build", "-t", "wheel", "-d", evidence/"dist"], cwd=ROOT)
    wheel = next((evidence/"dist").glob("*.whl"))
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        assert "companion/resources/manifests/analysis-mechanics.json" in names
        assert "companion/resources/schemas/multi-team.schema.json" in names
        assert not any(name.startswith((".local/", "tests/", "tools/")) for name in names)
    run("create-runtime", [sys.executable, "-m", "venv", "--without-pip", target/"运行 环境"])
    python = target/"运行 环境/Scripts/python.exe"
    uv = ROOT/".local/tools/uv/uv.exe"
    run("locked-dependencies", [uv, "pip", "sync", "--offline", "--require-hashes", "--python", python, ROOT/"requirements.lock"])
    run("install-wheel", [uv, "pip", "install", "--offline", "--no-deps", "--python", python, wheel])
    run("verify-import", [python, "-c", "import companion,sys; assert sys.prefix in companion.__file__; print(companion.__version__)"])
    player = target/"只读 玩家目录"

    def call(name, arguments, expected=0):
        return json.loads(run(name, [python, "-m", "companion", "--data-dir", player, "--offline", "call", name, "--input", "-"],
                              input=json.dumps(arguments, ensure_ascii=False), expected=expected))

    for mode in ("memory_of_chaos", "pure_fiction", "apocalyptic_shadow", "anomaly_arbitration"):
        schema = call("analysis_schema", {"mode": mode})
        arguments = {"mode": mode, **schema["data"]["example_request"]}
        result = call("mode_analyze", arguments)
        assert result["data"]["ranking_permitted"] and result["data"]["label"] == "简化比较"
        assert call("mode_analyze", {"mode": mode}, 3)["data"]["analysis_kind"] == "qualitative"
    sample = call("analysis_schema", {})["data"]["example_request"]["request"]
    assert call("sensitivity_analyze", {"request": sample, "axes": [{"field": "scenario.target_count", "values": [1, 2, 3]}], "max_seconds": 10})["data"]["reversal_conditions"]
    messages = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-11-25", "clientInfo": {"name": "p5-wheel", "version": "1"}, "capabilities": {}}},
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "simulation_compare", "arguments": {"request": sample}}}]
    wire = run("installed-mcp", [python, "-m", "companion", "--data-dir", player, "--offline", "mcp"], input="\n".join(json.dumps(item) for item in messages)+"\n")
    assert json.loads(wire.splitlines()[-1])["result"]["structuredContent"]["data"]["outcomes"][0]["expected_damage"] == 9720
    assert not player.exists(), "Read-only mode analyses initialized player data"
    call("account_configure", {"account_id": "p5-synthetic", "style": "A", "region": "ASIA"})
    saved = call("comparison_save", {"account_id": "p5-synthetic", "request": sample})
    replay = call("experiment_replay", {"account_id": "p5-synthetic", "experiment_id": saved["data"]["experiment_id"]})
    assert replay["data"]["same_result"]
    # Separate application processes, using the same real persisted database.
    call("memory_append", {"account_id": "p5-synthetic", "record_type": "conclusion", "title": "P5窗口比较", "body": "单目标200AV假设丹恒9720，黑塔5940；不是实战或抽卡收益。",
         "summary": "单目标假设下选择丹恒", "topic": "p5-acceptance", "game_version": "4.6", "conditions": ["E0无大行迹，单目标200AV"],
         "experiment_ids": [saved["data"]["experiment_id"]], "claim_key": "p5-window-choice"})
    memory = call("memory_search", {"account_id": "p5-synthetic", "query": "单目标", "topic": "p5-acceptance"})
    assert "单目标假设下选择丹恒" in json.dumps(memory, ensure_ascii=False)
    summary = {"at": datetime.now(timezone.utc).isoformat(), "status": "PASS", "commands": len(records),
               "wheel": str(wheel), "wheel_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(), "target": str(target),
               "layer": "actual wheel, fresh Windows venv, independent CLI/MCP processes, synthetic-only; not a new model conversation",
               "uid_queries": 0, "model_calls": 0, "evidence": str(evidence)}
    (evidence/"summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
