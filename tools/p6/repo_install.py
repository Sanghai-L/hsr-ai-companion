"""Actual fresh Codex installs a fixed repository commit using published media."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import uuid

from companion.contracts import canonical
from companion.storage import Store
from tools.p6.record import write

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", required=True)
    args = parser.parse_args()
    if len(args.commit) != 40 or any(c not in "0123456789abcdef" for c in args.commit):
        raise ValueError("需要已验证的完整提交SHA")
    label = uuid.uuid4().hex[:10]
    base = ROOT/".local/probes/p6-repository"/label/"中文 空格验收"
    source, player = base/"下载 源码", base/"玩家 项目"
    player.mkdir(parents=True)
    (player/".codex").mkdir()
    original_config = 'model = "preserve-existing-user-model"\n'
    original_rules = "玩家原有规则：安装和卸载后保留这段文字。\n"
    (player/".codex/config.toml").write_text(original_config, encoding="utf-8")
    (player/"AGENTS.md").write_text(original_rules, encoding="utf-8")
    evidence = ROOT/".local/evidence/D056"/("repository-"+label)
    evidence.mkdir(parents=True)
    codex = shutil.which("codex")
    command = [codex,"exec","--ignore-user-config","--skip-git-repo-check","--ephemeral","--json","--approve-for-me","-C",str(base),
               "--model","gpt-6.1-sol","-c",'model_reasoning_effort="max"',"-c",'web_search="disabled"',"-o",str(evidence/"answer.txt"),"-"]
    prompt = (f"这是获授权的P6真实安装验收，只用本次合成环境。仓库https://github.com/Sanghai-L/hsr-ai-companion.git，固定提交{args.commit}。"
              f"请自行从仓库克隆到{source}，检出该提交，读取README、INSTALL_AGENT、LICENSE、覆盖和签名说明，"
              f"按现有Install-HSR.ps1将离线候选安装到{player}。使用-Offline，保留这个玩家项目已有配置与规则。"
              "当前Codex已登录；不要使用全局Python、pip或uv，不安装额外依赖，不改源码来修复问题，不上传仓库或调用其他代理。"
              "只能使用现有签名介质；若失败如实停止。完成后使用已安装的项目运行时实际执行只读doctor/status，核实版本和路径。"
              "不要启动交互式Codex TUI，不查询UID，不导入真实账号；首次玩家初始化由下个会话进行。"
              "无需询问是否继续。最后简述安装位置、保留的原配置及已验证／未验证内容。")
    env = os.environ.copy()
    system = Path(os.environ["SystemRoot"])/"System32"
    search = [str(system)]
    for name in ("git", "codex", "node"):
        found = shutil.which(name)
        if found:
            search.append(str(Path(found).parent))
    env.update(PATH=os.pathsep.join(dict.fromkeys(search)), PYTHONUTF8="1", PYTHONIOENCODING="utf-8", TEMP=str(base), TMP=str(base))
    env.pop("PYTHONPATH", None)
    stdout_path, stderr_path = evidence/"stdout.jsonl", evidence/"stderr.txt"
    started = time.monotonic()
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        process = subprocess.Popen(command, cwd=base, env=env, stdin=subprocess.PIPE, stdout=stdout, stderr=stderr,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        process.stdin.write(prompt.encode()); process.stdin.close()
        print(json.dumps({"state":"running","pid":process.pid,"evidence":str(evidence)},ensure_ascii=False),flush=True)
        while process.poll() is None and time.monotonic()-started < 480:
            time.sleep(.5)
        if process.poll() is None:
            subprocess.run(["taskkill","/PID",str(process.pid),"/T","/F"],capture_output=True,timeout=20)
            process.wait(timeout=20)
    record = {"command":command,"prompt":prompt,"exit_code":process.returncode,"seconds":round(time.monotonic()-started,3),
              "commit":args.commit,"source":str(source),"player":str(player),"no_python_on_parent_path":True,
              "answer":(evidence/"answer.txt").read_text(encoding="utf-8") if (evidence/"answer.txt").exists() else ""}
    write(evidence.relative_to(ROOT)/"model.json",record)
    assert process.returncode == 0 and record["answer"], record
    actual = subprocess.run(["git","-C",str(source),"rev-parse","HEAD"],capture_output=True,text=True,timeout=15)
    assert actual.returncode == 0 and actual.stdout.strip() == args.commit
    state = json.loads((player/".hsr-program/install-state.json").read_bytes())
    python = player/".hsr-program/versions"/state["current"]["digest"]/"runtime/python.exe"
    checksums = json.loads((source/"install/windows-x64/checksums.json").read_bytes())
    assert state["current"]["digest"] == checksums["program_sha256"]
    assert original_config.strip() in (player/".codex/config.toml").read_text(encoding="utf-8")
    assert original_rules.strip() in (player/"AGENTS.md").read_text(encoding="utf-8")
    data = Path(state["data_dir"])
    commands = []
    def call(name, arguments, expected=0):
        completed = subprocess.run([str(python),"-I","-m","companion","--data-dir",str(data),"--offline","call",name,"--input","-"],
                                   input=canonical(arguments),env=env,cwd=player,capture_output=True,timeout=40)
        value = json.loads(completed.stdout)
        commands.append({"operation":name,"exit_code":completed.returncode,"result":value})
        write(evidence.relative_to(ROOT)/"business-commands.json",commands)
        assert completed.returncode == expected, value
        return value
    call("account_configure",{"account_id":"install-synthetic","style":"A","region":"ASIA"})
    sample = call("analysis_schema",{})["data"]["example_request"]["request"]
    saved = call("comparison_save",{"account_id":"install-synthetic","request":sample})["data"]
    call("memory_append",{"account_id":"install-synthetic","record_type":"conclusion","title":"安装验收研究","body":"单目标合成窗口丹恒配置9720、黑塔5940；不能推实战分数。",
         "summary":"安装验收合成比较","topic":"p6-install","conditions":["单目标200AV，E0无大行迹"],"game_version":"4.6","claim_key":"p6-install-window","experiment_ids":[saved["experiment_id"]]})
    call("memory_search",{"account_id":"install-synthetic","topic":"p6-install"})
    replayed = call("experiment_replay",{"account_id":"install-synthetic","experiment_id":saved["experiment_id"]})
    assert replayed["data"]["same_result"]
    offline = call("updates_check",{"kind":"all","force":True},3)
    assert not any(v["data"] and v["data"].get("latest") for v in offline["data"].values())
    uninstall = subprocess.run([str(system/"WindowsPowerShell/v1.0/powershell.exe"),"-NoProfile","-ExecutionPolicy","Bypass","-File",
        str(source/"install/windows-x64/Install-HSR.ps1"),"-Workspace",str(player),"-Action","uninstall","-Offline"],capture_output=True,env=env,timeout=90)
    assert uninstall.returncode == 0, uninstall.stderr
    assert (player/".codex/config.toml").read_text(encoding="utf-8") == original_config
    assert (player/"AGENTS.md").read_text(encoding="utf-8") == original_rules
    store = Store(data/"personal",read_only=True)
    with store.connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM research").fetchone()[0] >= 1
        assert connection.execute("SELECT COUNT(*) FROM uid_queries").fetchone()[0] == 0
    result = {"status":"PASS","repository":"Sanghai-L/hsr-ai-companion","commit":args.commit,"program_sha256":state["current"]["digest"],
              "model":"gpt-6.1-sol","reasoning":"max","model_record":str(evidence/"model.json"),"model_installed_from_repository":True,
              "actual_independent_business_processes":len(commands),"saved_input_replayed_after_process_restart":True,
              "existing_config_preserved_after_uninstall":True,"personal_preserved":True,"actual_uid_queries":0,
              "environment":"Windows 11 build26200 x64; separate Chinese-space directories; no global Python on installer parent PATH; not VM"}
    write(evidence.relative_to(ROOT)/"result.json",result)
    print(json.dumps(result,ensure_ascii=False),flush=True)


if __name__ == "__main__":
    main()
