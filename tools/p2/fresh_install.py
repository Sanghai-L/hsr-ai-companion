"""Build and exercise the actual wheel in a fresh Chinese/space-path venv."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid
import zipfile

from companion import __version__
from record import ROOT, now, write_json


def main():
    output = ROOT / ".local/evidence/D028"
    target = ROOT / ".local/probes/p2" / ("干净 安装验收 " + uuid.uuid4().hex[:8])
    target.mkdir(parents=True)
    environment = os.environ.copy()
    environment.update(PYTHONUTF8="1", PYTHONIOENCODING="utf-8", TEMP=str(ROOT / ".local/tmp"), TMP=str(ROOT / ".local/tmp"),
                       UV_CACHE_DIR=str(ROOT / ".local/cache/uv"), UV_PYTHON_DOWNLOADS="never", UV_LINK_MODE="copy")
    environment.pop("PYTHONPATH", None)
    commands = []

    def run(name, command, *, expected=0, input=None, cwd=target):
        process = subprocess.run([str(a) for a in command], cwd=cwd, env=environment, input=input, capture_output=True,
                                 text=True, encoding="utf-8", errors="replace", timeout=60)
        commands.append({"name": name, "command": [str(a) for a in command], "cwd": str(cwd), "exit_code": process.returncode,
                         "expected_exit_code": expected, "stdout": process.stdout, "stderr": process.stderr})
        write_json(".local/evidence/D028/fresh-install-commands.json", commands)
        if process.returncode != expected:
            raise RuntimeError(f"{name} failed: {process.stderr[-1000:]} {process.stdout[-2000:]}")
        return process.stdout

    run("build-wheel", [sys.executable, "-m", "hatchling", "build", "-t", "wheel", "-d", output / "dist"], cwd=ROOT)
    wheel = next((output / "dist").glob(f"hsr_ai_companion-{__version__}-*.whl"))
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        assert not any(name.startswith((".local/", "tests/")) for name in names)
        for name in ("schemas/evidence.schema.json", "migrations/0002_research.sql", "knowledge/bundle.json", "skills/research/SKILL.md", "skills/memory/SKILL.md", "skills/discussion/SKILL.md"):
            assert "companion/resources/"+name in names, name
    run("create-new-venv", [sys.executable, "-m", "venv", "--without-pip", target / "环境"])
    python = target / "环境/Scripts/python.exe"
    uv = ROOT / ".local/tools/uv/uv.exe"
    run("locked-dependencies", [uv, "pip", "sync", "--offline", "--require-hashes", "--python", python, ROOT / "requirements.lock"])
    run("install-built-wheel", [uv, "pip", "install", "--offline", "--no-deps", "--python", python, wheel])
    run("installed-import-resources", [python, "-c", "import companion,sys;from pathlib import Path;from companion.resources import resource_text;assert str(Path(sys.prefix)) in companion.__file__;assert 'memory_heads' in resource_text('migrations','0002_research.sql');assert 'description:' in resource_text('skills','research/SKILL.md');print(companion.__version__)"])
    data = target / "玩家 资料"

    def call(name, args, expected=0):
        return json.loads(run(name, [python, "-m", "companion", "--data-dir", data, "--offline", "call", name, "--input", "-", "--json"],
                              input=json.dumps(args, ensure_ascii=False), expected=expected))

    call("doctor", {})
    assert not data.exists()
    call("session_bootstrap", {}, 3)
    call("account_configure", {"account_id": "a", "style": "A", "uid": "100000001", "region": "ASIA"})
    call("account_configure", {"account_id": "b", "style": "B"})
    for account, amount in (("a", 0), ("b", 1600)):
        call("account_patch", {"account_id": account, "expected_snapshot_id": None, "fields": [{"entity_id": "account", "field_id": "stellar_jade",
            "quantity": {"value": amount, "unit": "count", "state": "known", "precision": None}, "basis": "record", "confirmed": True,
            "source": {"type": "synthetic", "ref": "P2 clean installation original fixture", "observed_at": now()}}]})
    assert call("account_get", {"account_id": "a"})["data"]["snapshot"]["fields"][0]["quantity"]["value"] == 0
    search = call("knowledge_search", {"query": "巡猎三月强化普攻", "version": "4.6"})
    assert "march-hunt" in {e["id"] for e in search["data"]["items"]}
    call("knowledge_read", {"entry_id": "march-hunt", "limit": 100})
    memory = call("memory_append", {"account_id": "a", "record_type": "conclusion", "title": "合成研究", "body": "旧结论", "summary": "旧结论",
        "topic": "test", "game_version": "4.6", "claim_key": "synthetic", "conditions": ["合成条件"], "source_refs": ["user:synthetic fixture"]})
    rid = memory["data"]["research_id"]
    assert call("memory_search", {"account_id": "b"})["data"]["items"] == []
    assert call("memory_search", {"account_id": "a"})["data"]["items"][0]["research_id"] == rid
    assert call("session_bootstrap", {}, 3)["data"]["memory"]["data"]["items"]
    evidence = call("evidence_register", {"account_id": "a", "claim": "synthetic", "url": "https://example.com/controlled-test", "content": "合成新证据", "kind": "manual", "stance": "opposes"})
    proposal = call("memory_conflict_propose", {"account_id": "a", "research_id": rid, "evidence_ids": [evidence["data"]["registered_id"]], "reason": "合成反例", "new_body": "新结论", "new_summary": "新结论"})
    call("memory_revision_apply", {"account_id": "a", "plan_id": proposal["data"]["plan_id"], "expected_id": rid, "confirmation_id": "not-a-user-reply"}, 2)
    assert call("memory_read", {"account_id": "a", "research_id": rid})["data"]["content"] == "旧结论"
    call("account_refresh", {"account_id": "a", "request_ref": "synthetic offline import request", "purpose": "import"}, 4)
    call("source_fetch", {"url": "https://raw.githubusercontent.com/EnkaNetwork/API-docs/master/api.md"}, 3)
    run("install-project-skills", [python, "-c", "import sys;from companion.adapters.codex import install_codex;print(install_codex(sys.argv[1],sys.executable,sys.argv[2],offline=True))", target / "玩家 项目", data])
    assert (target / "玩家 项目/.agents/skills/memory/SKILL.md").is_file()
    write_json(".local/evidence/D028/fresh-install-summary.json", {"at": now(), "state": "PASS", "wheel": str(wheel),
        "wheel_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(), "target": str(target), "commands": len(commands), "failures": 0,
        "layer": "actual wheel in new isolated venv and Chinese space path; separate processes; synthetic-only offline", "uid_queries": 0})
    print(json.dumps({"state": "PASS", "commands": len(commands), "target": str(target)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
