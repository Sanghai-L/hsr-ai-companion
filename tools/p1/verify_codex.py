"""Bounded actual Codex acceptance, separate from offline protocol tests."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from companion.adapters.codex import install_codex

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=["foundation", "onboarded", "restart"], required=True)
    args = parser.parse_args()
    workspace = ROOT / ".local/probes/p1/Codex 中文 空格项目"
    data_dir = workspace / ".local/player"
    install_codex(workspace, sys.executable, data_dir, offline=True)
    task = "D018" if args.phase == "foundation" else "D020"
    evidence = ROOT / f".local/evidence/{task}/codex-{args.phase}.json"
    if evidence.exists():
        raise RuntimeError("Acceptance already exists; inspect it before explicitly archiving/retrying")
    evidence.parent.mkdir(parents=True, exist_ok=True)
    setup = json.loads((ROOT / ".local/evidence/D005/host-setup-status.json").read_bytes())
    selection = setup["codex"]["model_selection"]
    command = [shutil.which("codex"), "exec", "--ignore-user-config", "--ephemeral", "--skip-git-repo-check",
               "--json", "-C", str(workspace),
               "-o", str(evidence.with_suffix(".answer.txt"))]
    if selection.get("model"):
        command += ["--model", selection["model"]]
    overrides = ["web_search=\"disabled\"", *json.loads((workspace / ".hsr-companion/mcp-overrides.json").read_bytes())]
    if selection.get("model_reasoning_effort"):
        overrides.append("model_reasoning_effort=" + json.dumps(selection["model_reasoning_effort"]))
    # Only genuinely read-only tools get this test-session read approval.
    overrides += [f'mcp_servers.hsr_companion.tools.{name}.approval_mode="approve"' for name in ("status", "doctor", "capabilities")]
    if args.phase != "foundation":
        command += ["--approve-for-me"]
    else:
        command += ["--sandbox", "read-only"]
    for value in overrides:
        command += ["-c", value]
    command.append("你好，介绍一下现在能帮我做什么，简短回答。")
    environment = os.environ.copy()
    environment.update(PYTHONUTF8="1", PYTHONIOENCODING="utf-8", TEMP=str(ROOT / ".local/tmp"), TMP=str(ROOT / ".local/tmp"))
    started = time.perf_counter()
    process = subprocess.Popen(command, cwd=workspace, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, encoding="utf-8", errors="replace")
    timed_out = False
    try:
        stdout, stderr = process.communicate(timeout=150)
    except subprocess.TimeoutExpired:
        timed_out = True
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True)
        stdout, stderr = process.communicate(timeout=10)
    expected = "status" if args.phase == "foundation" else "session_bootstrap"
    calls = []
    for line in stdout.splitlines():
        try:
            item = json.loads(line).get("item", {})
        except ValueError:
            continue
        if item.get("type") == "mcp_tool_call" and item.get("server") == "hsr_companion" and item.get("status") == "completed":
            calls.append(item)
    tool_called = any(item.get("tool") == expected and not item.get("error") and item.get("result") is not None for item in calls)
    record = {"at": datetime.now(timezone.utc).isoformat(), "args": command, "pid": process.pid,
              "exit_code": process.returncode, "seconds": round(time.perf_counter()-started, 3),
              "timeout": timed_out, "stdout": stdout, "stderr": stderr,
              "layer": "actual fresh Codex session with installed per-session MCP adapter and normal greeting",
              "no_uid_query": True, "global_config_changed": False, "expected_tool": expected,
              "tool_called": tool_called, "completed_tools": [i.get("tool") for i in calls],
              "accepted": process.returncode == 0 and not timed_out and tool_called}
    evidence.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"evidence": str(evidence), "exit_code": process.returncode, "timeout": timed_out,
                      "stdout_tail": stdout[-3500:], "stderr_tail": stderr[-1000:]}, ensure_ascii=False))
    return 0 if record["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

