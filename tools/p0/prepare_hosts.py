"""Prepare isolated host workspaces; do not modify user profiles or call models."""
import json
import os
from pathlib import Path
import shutil

from common import ROOT, LOCAL, command, write_json, update_task


def main():
    update_task("D005", "IN_PROGRESS", summary="按用户追加要求仅验证 Codex／DSH；准备隔离 MCP 探针",
                next_step="工具协议、真实宿主调用和重启复测", level="待实测")
    python = LOCAL / "probes/mcp/中文 空格验证/Scripts/python.exe"
    probe = ROOT / "tools/p0/mcp_probe.py"
    for host in ("codex", "dsh"):
        workspace = LOCAL / "probes/hosts" / host / "中文 空格项目"
        workspace.mkdir(parents=True, exist_ok=True)
        (workspace / "AGENTS.md").write_text(
            "# P0 探针项目\n\n本项目的规则标记为 STAR-RAIL-P0-RULE-20261106。\n"
            "当用户开始正常交流时，先调用 probe_status，随后简短回答；不要求启动口令。\n"
            "回答中包含本项目的规则标记，供本轮检查规则是否自动加载。\n"
            "此工具只有版本和固定文本；不会查询 UID。不得读取本项目外的用户数据。\n", encoding="utf-8")
        if host == "codex":
            # A generated local example, not the user's global config.
            text = ('[mcp_servers.hsr_p0]\ncommand = '+json.dumps(str(python))+'\nargs = ['+json.dumps(str(probe))+']\n'
                    '[mcp_servers.hsr_p0.tools.probe_status]\napproval_mode = "approve"\n')
            folder = workspace / ".codex"
            folder.mkdir(exist_ok=True)
            (folder / "config.toml").write_text(text, encoding="utf-8")
        else:
            (workspace / "mcp-plugin-entry.yaml").write_text(
                "- id: hsr-p0\n  name: '@deepseek-ai/dsh-mcp-client'\n  config:\n"
                "    serverName: hsr_p0\n    transport: stdio\n"
                f"    command: {json.dumps(str(python))}\n"
                f"    args: [{json.dumps(str(probe))}]\n"
                "    failOnStartupError: true\n    startupTimeoutMs: 10000\n", encoding="utf-8")
    env = os.environ.copy()
    env["CODEX_HOME"] = str(LOCAL / "probes/host-home")
    env["DSH_HOME"] = str(LOCAL / "probes/dsh-home")
    Path(env["DSH_HOME"]).mkdir(parents=True, exist_ok=True)
    for name, args in [
        ("codex-help", [shutil.which("codex"), "--help"]),
        ("codex-mcp-help", [shutil.which("codex"), "mcp", "--help"]),
        ("dsh-version", [r"E:\Deepseek Harness\resources\runtime\cli\bin\dsh.cmd", "--version"]),
        ("dsh-headless-help", [r"E:\Deepseek Harness\resources\runtime\cli\bin\dsh.cmd", "headless", "--help"]),
    ]:
        record = command(args, task="D005", name=name, env=env, timeout=30)
        print(json.dumps({"step": name, "exit_code": record["exit_code"]}))


if __name__ == "__main__":
    main()
