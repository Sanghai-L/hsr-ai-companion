"""Fresh wheel install and synthetic P1 lifecycle, with exact command evidence."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / ".local/evidence/D020"


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, help="Fresh project-local verification directory")
    args = parser.parse_args()
    target = Path(args.output).resolve()
    if not target.is_relative_to(ROOT / ".local") or target.exists():
        raise RuntimeError("Use a fresh directory under project .local; never overwrite existing player data")
    target.mkdir(parents=True)
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    environment.update(PYTHONUTF8="1", PYTHONIOENCODING="utf-8", TEMP=str(ROOT / ".local/tmp"), TMP=str(ROOT / ".local/tmp"),
                       UV_CACHE_DIR=str(ROOT / ".local/cache/uv"), UV_PYTHON_DOWNLOADS="never", UV_LINK_MODE="copy")
    environment.pop("PYTHONPATH", None)
    commands = []

    def run(name, command, *, expected=0, input=None, cwd=target):
        process = subprocess.run([str(a) for a in command], cwd=cwd, env=environment, input=input,
                                 capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
        record = {"name": name, "command": [str(a) for a in command], "cwd": str(cwd), "exit_code": process.returncode,
                  "expected_exit_code": expected, "stdout": process.stdout, "stderr": process.stderr}
        commands.append(record)
        write(EVIDENCE / "fresh-install-commands.json", commands)
        if process.returncode != expected:
            raise RuntimeError(f"{name}: {process.returncode}, expected {expected}: {process.stderr[-1500:]} {process.stdout[-1500:]}")
        return process.stdout

    run("build-wheel", [sys.executable, "-m", "hatchling", "build", "-t", "wheel", "-d", EVIDENCE / "dist"], cwd=ROOT)
    wheel = next((EVIDENCE / "dist").glob("hsr_ai_companion-*.whl"))
    run("create-clean-environment", [sys.executable, "-m", "venv", "--without-pip", target / "环境"])
    python = target / "环境/Scripts/python.exe"
    uv = ROOT / ".local/tools/uv/uv.exe"
    run("install-locked-dependencies-offline", [uv, "pip", "sync", "--offline", "--require-hashes", "--python", python, ROOT / "requirements.lock"])
    run("install-wheel-offline", [uv, "pip", "install", "--offline", "--no-deps", "--python", python, wheel])
    run("wheel-import-from-clean-cwd", [python, "-c", "import companion,sys; from pathlib import Path; from companion.resources import resource_text; assert str(Path(sys.prefix)) in companion.__file__; assert 'CREATE TABLE' in resource_text('migrations','0001_initial.sql'); print(companion.__file__)"])
    run("module-help", [python, "-m", "companion", "--help"])
    data = target / "玩家 资料"

    def call(name, arguments, expected=0):
        output = run(name, [python, "-m", "companion", "--data-dir", data, "--offline", "call", name, "--input", "-", "--json"],
                     expected=expected, input=json.dumps(arguments, ensure_ascii=False))
        return json.loads(output)

    call("doctor", {})
    assert not data.exists(), "doctor must not initialize data"
    initial = call("session_bootstrap", {}, 3)
    assert initial["missing_fields"] == ["account", "style"]
    for account, style, uid in [("synthetic-a", "A", "000000001"), ("synthetic-b", "B", "000000002")]:
        call("account_configure", {"account_id": account, "label": "纯合成验收账号", "uid": uid, "region": "ASIA", "style": style})
    def manual(account, value):
        return call("account_manual_update", {"account_id": account, "fields": [{"entity_id": "account", "field_id": "stellar_jade",
            "quantity": {"value": value, "unit": "count", "state": "unknown" if value is None else "known", "precision": None},
            "source": {"type": "synthetic", "ref": "P1-gate-original", "observed_at": "2026-11-06T00:00:00Z"}, "confirmed": True, "basis": "record"}]})
    manual("synthetic-a", 0)
    manual("synthetic-b", None)
    call("account_select", {"account_id": "synthetic-b"})
    assert call("account_get", {})["data"]["snapshot"]["fields"][0]["quantity"]["value"] is None
    assert call("account_get", {"account_id": "synthetic-a"})["data"]["snapshot"]["fields"][0]["quantity"]["value"] == 0
    restarted = call("session_bootstrap", {}, 3)
    assert not restarted["missing_fields"] and restarted["data"]["state"]["style"] == "B"
    assert restarted["data"]["uid_import"] == "pending" and restarted["data"]["uid_refreshed"] is False

    from companion.knowledge.package import build_package
    source = target / "维护者 知识源"
    program = target / "维护者 程序源"
    source.mkdir()
    program.mkdir()
    def publish(version, minimum="0.1.0", maximum="0.1.99"):
        package = build_package(ROOT / "tests/fixtures/knowledge/source", version=version, program_min=minimum, program_max=maximum)
        (source / "knowledge.json").write_bytes(package.encode())
        write(source / "release.json", {"kind": "knowledge", "version": version, "sha256": hashlib.sha256(package.encode()).hexdigest(),
                                        "size": len(package.encode()), "artifact": "knowledge.json"})
    publish("0.1.0")
    write(program / "release.json", {"kind": "program", "version": "0.2.0", "sha256": "a" * 64, "size": 2, "artifact": "program.json"})
    write(data / "config.json", {"knowledge_source": str(source), "program_source": str(program), "check_interval": 60})
    database = data / "personal/personal.sqlite3"
    before = hashlib.sha256(database.read_bytes()).hexdigest()
    assert call("knowledge_sync", {"force": True})["data"]["version"] == "0.1.0"
    publish("0.2.0")
    assert call("knowledge_sync", {"force": True})["data"]["version"] == "0.2.0"
    publish("0.3.0", "9.0.0", "9.1.0")
    failed = call("knowledge_sync", {"force": True}, 3)
    assert failed["error"]["code"] == "VERSION_INCOMPATIBLE" and failed["data"]["latest"] is False
    assert hashlib.sha256(database.read_bytes()).hexdigest() == before
    proposal = call("program_update_propose", {"target_version": "0.2.0"})
    assert proposal["data"]["installed"] is False and proposal["data"]["plan"]["state"] == "proposed"
    assert not (program / "program.json").exists(), "Program check must not fetch/install the proposed artifact"
    call("program_update_apply", {"confirmed": True}, 3)
    call("account_refresh", {}, 3)
    from companion.updates.knowledge import KnowledgeSync
    installed = KnowledgeSync(data / "knowledge")
    current = installed.current()
    installed.files.path(f"packages/{current.fingerprint}/index.json").write_bytes(b"[]")
    assert installed.recover() == {"version": "0.1.0", "recovered": True}

    # Prepare the installed host's synthetic state; no real UID or network request.
    from companion.accounts import AccountService
    from companion.services.context import Context
    host_dir = ROOT / ".local/probes/p1/Codex 中文 空格项目/.local/player"
    accounts = AccountService(Context(host_dir, offline=True).store)
    accounts.configure("synthetic-a", label="工程验收合成 A", uid="000000001", region="ASIA", style="A")
    accounts.configure("synthetic-b", label="工程验收合成 B", uid="000000002", region="ASIA", style="B", make_default=True)
    report = {"at": datetime.now(timezone.utc).isoformat(), "status": "PASS", "fresh_root": str(target),
              "wheel": str(wheel), "wheel_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
              "commands": len(commands), "command_failures": 0, "uid_network_requests": 0,
              "model_requests_in_this_script": 0, "knowledge_private_db_unchanged": True,
              "program_installed": False, "layer": "actual clean venv wheel install and synthetic local CLI lifecycle"}
    write(EVIDENCE / "fresh-install-summary.json", report)
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()

