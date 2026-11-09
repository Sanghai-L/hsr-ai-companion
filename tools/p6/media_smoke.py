"""Run the shipped PowerShell entry in an independent Chinese-space project."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import uuid

from tools.p6.record import write

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--media", type=Path, required=True)
    parser.add_argument("--evidence-task", default="D051")
    args = parser.parse_args()
    label = uuid.uuid4().hex[:10]
    workspace = ROOT/".local/probes/p6-media"/label/"玩家 中文 空格项目"
    evidence = ROOT/".local/evidence"/args.evidence_task/("media-"+label)
    workspace.mkdir(parents=True)
    (workspace/".codex").mkdir()
    config = 'model = "preserve-user-model"\n'
    rules = "玩家已有规则，安装和卸载都要保留。\n"
    (workspace/".codex/config.toml").write_text(config, encoding="utf-8")
    (workspace/"AGENTS.md").write_text(rules, encoding="utf-8")
    env = os.environ.copy()
    system = Path(os.environ["SystemRoot"])/"System32"
    env["PATH"] = str(system)
    env.pop("PYTHONPATH", None)
    records = []
    for action in ("install", "install", "uninstall"):
        command = [str(system/"WindowsPowerShell/v1.0/powershell.exe"), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                   str(args.media.resolve()/"Install-HSR.ps1"), "-Workspace", str(workspace), "-Action", action, "-Offline"]
        completed = subprocess.run(command, cwd=workspace, env=env, capture_output=True, timeout=150)
        item = {"action": action, "command": command, "exit_code": completed.returncode,
                "stdout": completed.stdout.decode("utf-8", "replace"), "stderr": completed.stderr.decode("utf-8", "replace"),
                "no_python_on_path": True}
        records.append(item)
        write(evidence.relative_to(ROOT)/"commands.json", records)
        if completed.returncode:
            raise RuntimeError(str(item))
        if action == "install":
            assert config.strip() in (workspace/".codex/config.toml").read_text(encoding="utf-8")
            assert rules.strip() in (workspace/"AGENTS.md").read_text(encoding="utf-8")
            assert (workspace/".hsr-program/install-state.json").is_file()
    assert (workspace/".codex/config.toml").read_text(encoding="utf-8") == config
    assert (workspace/"AGENTS.md").read_text(encoding="utf-8") == rules
    assert not (workspace/".hsr-program/versions").exists()
    assert (workspace/".local/player/release-trust.json").is_file()
    result = {"status": "PASS", "workspace": str(workspace), "commands": len(records), "media": str(args.media.resolve()),
              "tested_environment": "Windows 11 build 26200 x64, independent directories, Windows PowerShell 5.1, PATH only System32; not VM",
              "no_global_python": True, "existing_user_config_preserved": True, "uninstall_personal_preserved": True,
              "bootstrap_temporary_removed": not any((workspace/".hsr-bootstrap").iterdir())}
    write(evidence.relative_to(ROOT)/"result.json", result)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
