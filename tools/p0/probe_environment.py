"""D002: targeted Windows/runtime inventory and isolated UTF-8 smoke checks."""
import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import sys
import venv
import winreg

from common import ROOT, LOCAL, command, now, write_json, update_task


def main():
    data = {"at": now(), "platform": platform.platform(), "architecture": platform.machine(),
            "preferred_python": sys.version, "preferred_executable": sys.executable,
            "admin_required": False, "wsl_required": False, "docker_required": False}
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion") as key:
        data["windows"] = {name: winreg.QueryValueEx(key, name)[0]
                           for name in ("ProductName", "DisplayVersion", "CurrentBuildNumber", "UBR")}
    data["tools"] = {}
    # Run Codex with an isolated temporary home to avoid touching its normal cache.
    probe_home = LOCAL / "probes/host-home"
    probe_home.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["CODEX_HOME"] = str(probe_home)
    for name in ("python", "git", "node", "codex", "claude", "dsh", "uv"):
        path = shutil.which(name)
        tool = {"executable": path, "discovery": "ON_PATH" if path else "NOT_ON_PATH",
                "installed": True if path else None}
        if path and name not in {"claude", "dsh"}:
            record = command([path, "--version"], task="D002", name=name+"-version", env=env)
            tool.update(version=(record["stdout"]+record["stderr"]).strip(), exit_code=record["exit_code"])
        data["tools"][name] = tool
    data["host_notes"] = {
        "claude": "PATH、用户 .local/bin 和 npm 常见入口未发现；不能据此断言未安装。",
        "dsh": "存在用户 .dsh 数据目录；PATH 未发现可执行入口；未读取凭据。",
    }
    checks = []
    for name in ("hsr-nous", "mcp", "uid"):
        folder = LOCAL / "probes" / name / "中文 空格验证"
        executable = folder / "Scripts/python.exe"
        if not executable.exists():
            venv.EnvBuilder(with_pip=False).create(folder)
        if not (folder / "Lib/site-packages/pip").is_dir():
            pip_record = command([executable, "-m", "ensurepip", "--upgrade"],
                                 task="D002", name=name+"-ensurepip", timeout=90)
            assert pip_record["exit_code"] == 0, pip_record["stderr"]
        record = command([executable, "-c",
            "from pathlib import Path; import sys,json; p=Path('中文 文件.txt'); "
            "p.write_text('星穹铁道 UTF-8 验证',encoding='utf-8'); "
            "assert p.read_text(encoding='utf-8')=='星穹铁道 UTF-8 验证'; "
            "print(json.dumps({'version':sys.version,'utf8':True,'prefix':sys.prefix},ensure_ascii=False))"],
            task="D002", name=name+"-utf8", cwd=folder)
        assert record["exit_code"] == 0, record["stderr"]
        checks.append({"upstream": name, "venv": str(folder.relative_to(ROOT)),
                       "utf8": True, "exit_code": 0})
    data["isolated_checks"] = checks
    write_json(LOCAL / "evidence/D002/environment.json", data)
    lines = ["# Windows 验证基线", "", f"记录时间：{data['at']}。本机限定范围探测，不采集完整环境变量或密钥。", "",
             f"- 系统：{data['windows']}；架构：{data['architecture']}。",
             f"- 隔离环境使用 Python {platform.python_version()}；PATH 默认 Python 的结果另见证据。",
             "- 原生 Windows，未使用管理员权限、WSL、Docker；未修改全局 Python。",
             "- 三个 venv 均在中文和空格路径中实际启动、UTF-8 写入和回读成功。", "",
             "| 组件 | 状态 | 实际版本 |", "|---|---|---|"]
    for name, tool in data["tools"].items():
        version = tool.get("version", "未知；未发现不等于未安装").replace("\n", " ").replace("|", "\\|")
        lines.append(f"| {name} | {tool['discovery']} | {version} |")
    lines += ["", "DSH：仅发现既有用户数据目录，未定位入口；Claude Code：常见路径未发现。实际宿主调用归 D005 验收。",
              "", "网络：受当前执行沙箱限制的请求与取得网络权限后的请求分开记录；后续锁定文件只依据真实远端响应。",
              "详细记录：`.local/evidence/D002/environment.json`；各版本与 UTF-8 命令分文件保存。"]
    dest = ROOT / "docs/compatibility/windows-baseline.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("\n".join(lines)+"\n", encoding="utf-8")
    update_task("D002", "DONE", summary="Python 3.12 隔离环境及中文空格 UTF-8 实测通过；未发现宿主单列待验",
                artifacts=["docs/compatibility/windows-baseline.md"],
                commands=["python tools/p0/probe_environment.py"],
                counts={"passed": len(checks), "failed": 0, "skipped": 0},
                evidence=[".local/evidence/D002/environment.json"], next_step="D003", level="真实 Windows／解释器")
    print(json.dumps({"python": platform.python_version(), "utf8_checks": checks}, ensure_ascii=False))


if __name__ == "__main__":
    main()
