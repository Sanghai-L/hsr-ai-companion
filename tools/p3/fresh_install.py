"""Exercise quantitative tools from the actual wheel in a fresh runtime."""
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
    output = ROOT / ".local/evidence/D034"
    target = ROOT / ".local/probes/p3" / ("干净 安装验收 " + uuid.uuid4().hex[:8])
    target.mkdir(parents=True)
    environment = os.environ.copy()
    environment.update(PYTHONUTF8="1", PYTHONIOENCODING="utf-8", TEMP=str(ROOT/".local/tmp"), TMP=str(ROOT/".local/tmp"),
                       UV_CACHE_DIR=str(ROOT/".local/cache/uv"), UV_PYTHON_DOWNLOADS="never", UV_LINK_MODE="copy")
    environment.pop("PYTHONPATH",None)
    commands = []

    def run(name, args, *, expected=0, input=None, cwd=target):
        process = subprocess.run([str(a) for a in args],cwd=cwd,env=environment,input=input,capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=60)
        commands.append({"name":name,"command":[str(a) for a in args],"cwd":str(cwd),"exit_code":process.returncode,
                         "expected_exit_code":expected,"stdout":process.stdout,"stderr":process.stderr})
        write_json(".local/evidence/D034/fresh-install-commands.json",commands)
        if process.returncode != expected:
            raise RuntimeError(f"{name}: {process.stderr[-1500:]} {process.stdout[-1500:]}")
        return process.stdout

    run("build-wheel",[sys.executable,"-m","hatchling","build","-t","wheel","-d",output/"dist"],cwd=ROOT)
    wheel = next((output/"dist").glob(f"hsr_ai_companion-{__version__}-*.whl"))
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        assert not any(n.startswith((".local/","tests/","tools/")) for n in names)
        for name in ("experiment","comparison","damage-parameters","timeline-parameters","banner-rules","gacha-parameters","pull-plan-parameters"):
            assert f"companion/resources/schemas/{name}.schema.json" in names
    run("create-clean-venv",[sys.executable,"-m","venv","--without-pip",target/"环境"])
    python = target/"环境/Scripts/python.exe"
    uv = ROOT/".local/tools/uv/uv.exe"
    run("install-locked-dependencies",[uv,"pip","sync","--offline","--require-hashes","--python",python,ROOT/"requirements.lock"])
    run("install-built-wheel",[uv,"pip","install","--offline","--no-deps","--python",python,wheel])
    run("verify-installed-import",[python,"-c","import companion,sys;from pathlib import Path;assert str(Path(sys.prefix)) in companion.__file__;print(companion.__version__)"])
    data = target/"玩家 资料"

    def call(operation, arguments, expected=0):
        return json.loads(run(operation,[python,"-m","companion","--data-dir",data,"--offline","call",operation,"--input","-","--json"],
                              input=json.dumps(arguments,ensure_ascii=False),expected=expected))

    samples = {}
    contracts = {}
    for name,operation in (("damage","calculate"),("timeline","calculate"),("gacha","calculate"),("pull-plan","plan_pulls")):
        kind = "pull_plan" if name == "pull-plan" else name
        contracts[name] = call("calculation_schema", {"kind": kind})
        payload = contracts[name]["data"]["example_request"]
        samples[name] = call(operation,payload)
    assert samples["damage"]["data"]["result"]["value"] == 2025
    assert [e["at"] for e in samples["timeline"]["data"]["result"]["events"] if e["kind"]=="basic"] == [75,125,175]
    assert samples["gacha"]["data"]["result"]["probability_range"] == [.5,.5]
    assert samples["pull-plan"]["data"]["result"]["options"][1]["scenarios"]["neutral"]["all_targets_probability"] == .25
    assert not data.exists(), "Read-only calculations must not create player data"
    unknown = json.loads((ROOT/"tests/fixtures/requests/gacha.json").read_bytes())
    unknown["experiment"]["parameters"]["state"]["pity"] = None
    assert call("calculate",unknown,3)["data"]["result"]["probability_range"] == [.5,1]
    missing = json.loads((ROOT/"tests/fixtures/requests/damage.json").read_bytes())
    del missing["experiment"]["parameters"]["crit_rate"]
    assert call("calculate",missing,3)["error"]["code"] == "MISSING_DATA"
    assert call("simulation_submit",{},3)["error"]["code"] == "UNSUPPORTED"
    messages = [{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-11-25","clientInfo":{"name":"p3-wheel","version":"1"},"capabilities":{}}},
                {"jsonrpc":"2.0","method":"notifications/initialized"},
                {"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"calculate","arguments":json.loads((ROOT/"tests/fixtures/requests/damage.json").read_bytes())}}]
    wire = run("installed-wheel-mcp",[python,"-m","companion","--data-dir",data,"--offline","mcp"],input="\n".join(json.dumps(m) for m in messages)+"\n")
    assert json.loads(wire.splitlines()[-1])["result"]["structuredContent"]["data"]["result"]["value"] == 2025
    assert not data.exists()
    call("session_bootstrap",{},3)
    call("account_configure",{"account_id":"synthetic-a","style":"A","region":"ASIA"})
    call("account_configure",{"account_id":"synthetic-b","style":"B","region":"ASIA"})
    run("install-project-skills",[python,"-c","import sys;from companion.adapters.codex import install_codex;print(install_codex(sys.argv[1],sys.executable,sys.argv[2],offline=True))",target/"玩家 项目",data])
    assert "P3" in (target/"玩家 项目/.agents/skills/research/SKILL.md").read_text(encoding="utf-8")
    write_json(".local/evidence/D034/fresh-install-summary.json",{"at":now(),"status":"PASS","wheel":str(wheel),"wheel_sha256":hashlib.sha256(wheel.read_bytes()).hexdigest(),
               "target":str(target),"commands":len(commands),"failed":0,"uid_queries":0,
               "scope":"actual built wheel, new venv, Chinese-space paths, independent CLI/MCP processes; synthetic-only offline"})
    print(json.dumps({"status":"PASS","commands":len(commands),"target":str(target)},ensure_ascii=False))


if __name__ == "__main__":
    main()
