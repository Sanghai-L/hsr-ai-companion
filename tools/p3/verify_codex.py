"""Actual Codex acceptance in a fresh project; never modifies global settings."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from companion.adapters.codex import install_codex
from companion.accounts import AccountService
from companion.storage import Store
from record import ROOT, now, write_json

WORKSPACE = ROOT / ".local/probes/p3/Codex 中文 空格项目"
DATA = WORKSPACE / ".local/player"


def envelope(item):
    result = item.get("result") or {}
    for key in ("structured_content", "structuredContent"):
        if key in result:
            return result[key]
    for block in result.get("content", []):
        if block.get("type") == "text":
            try:
                return json.loads(block["text"])
            except ValueError:
                pass
    return {}


def run_turn(prompt, label):
    evidence = ROOT / f".local/evidence/D034/codex-{label}.json"
    if evidence.exists():
        raise RuntimeError("Preserve previous host evidence; use a new label")
    command = [shutil.which("codex"),"exec","--ignore-user-config","--skip-git-repo-check","--json","-C",str(WORKSPACE),
               "--approve-for-me","-o",str(evidence.with_suffix(".answer.txt"))]
    setup = json.loads((ROOT / ".local/evidence/D005/host-setup-status.json").read_bytes())["codex"]["model_selection"]
    if setup.get("model"):
        command += ["--model", setup["model"]]
    overrides = ['web_search="disabled"', *json.loads((WORKSPACE / ".hsr-companion/mcp-overrides.json").read_bytes())]
    if setup.get("model_reasoning_effort"):
        overrides.append("model_reasoning_effort=" + json.dumps(setup["model_reasoning_effort"]))
    for override in overrides:
        command += ["-c",override]
    command.append("-")
    environment = os.environ.copy()
    environment.update(PYTHONUTF8="1",PYTHONIOENCODING="utf-8",TEMP=str(ROOT/".local/tmp"),TMP=str(ROOT/".local/tmp"))
    process = subprocess.Popen(command,cwd=WORKSPACE,env=environment,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                               text=True,encoding="utf-8",errors="replace")
    started, timeout = time.monotonic(), False
    try:
        stdout, stderr = process.communicate(prompt,timeout=240)
    except subprocess.TimeoutExpired:
        timeout = True
        subprocess.run(["taskkill","/PID",str(process.pid),"/T","/F"],capture_output=True,timeout=15)
        stdout, stderr = process.communicate(timeout=10)
    events = []
    for line in stdout.splitlines():
        try:
            events.append(json.loads(line))
        except ValueError:
            pass
    calls = [e["item"] for e in events if e.get("item",{}).get("type") == "mcp_tool_call" and e["item"].get("status") == "completed"]
    answer = evidence.with_suffix(".answer.txt").read_text(encoding="utf-8") if evidence.with_suffix(".answer.txt").exists() else ""
    record = {"at":now(),"command":command,"prompt":prompt,"pid":process.pid,"exit_code":process.returncode,"timeout":timeout,
              "seconds":round(time.monotonic()-started,3),"stdout":stdout,"stderr":stderr,"answer":answer,
              "session_id":next((e.get("thread_id") for e in events if e.get("type")=="thread.started"),None),
              "tools":[{"name":c.get("tool"),"arguments":c.get("arguments"),"envelope":envelope(c)} for c in calls],
              "shell_calls":sum(e.get("type")=="item.completed" and e.get("item",{}).get("type")=="command_execution" for e in events),
              "layer":"actual installed Codex and project MCP; no mocked model responses"}
    write_json(evidence,record)
    print(json.dumps({"label":label,"exit_code":process.returncode,"seconds":record["seconds"],"tools":[c["name"] for c in record["tools"]],
                      "answer":answer,"stderr_tail":stderr[-350:]},ensure_ascii=False),flush=True)
    if timeout or process.returncode or not answer.strip():
        raise RuntimeError("Actual host turn failed; preserve and inspect evidence")
    if any(c["name"]=="account_refresh" for c in record["tools"]):
        raise RuntimeError("Host attempted unexpected UID query")
    return record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--case",choices=["timeline","pulls","damage","unknown"],required=True)
    parser.add_argument("--label")
    args = parser.parse_args()
    WORKSPACE.mkdir(parents=True,exist_ok=True)
    install_codex(WORKSPACE,sys.executable,DATA,offline=True)
    accounts = AccountService(Store(DATA/"personal"))
    if not accounts.list():
        accounts.configure("p3-demo",style="A",region="ASIA",make_default=True)
    common = "这是 P3 合成验收，账号 p3-demo，风格 A；暂不提供 UID，也不导入。用已安装工具计算，不写脚本，不读应用源码。按 4.6、synthetic 投资口径、local-analysis 模式，数据版本 p3-fixtures-1，知识 0.2.0，规则 p3-1，执行版本用工具当前 schema。来源记 synthetic:p3-scripted-player，所有非游戏条件都是我明确给出的合成假设；计算预算最多 100 个事件、1000 AV、3000000 个递推状态、10 秒。简短回答但保留影响结论的条件。\n"
    prompts = {
        "timeline": "只分析角色 A 的局部时序：初始速度100、能量0、上限100、回能效率增量0；每次普攻消耗0战技点、产生1战技点、回能20且吃回能效率，无其他效果；初始战技点0，上限5，循环普攻。AV50速度改为200，计算到AV175。第几AV行动？结束战技点和能量多少？解释为何不能从头重算行动时间，不要把局部分析说成整场模拟。",
        "pulls": "合成小卡池 toy-half-then-guarantee，pool_type synthetic，hard_pity=2，featured_rate=1，hazards=[0.5,1]，curve_kind=synthetic，来源 synthetic:exhaustive-two-pull-tree，note=仅验证算法非游戏卡池；初始pity0、guaranteed=false。今天2026-11-08预算160星琼、0票，reserve_pulls=0。2026-11-09一笔收入id single-original-event，来源synthetic:one-time-income，保守0星琼0票，中性0星琼1票，乐观160星琼1票。比较只抽一个新角色和补队连续抽两个不同目标，截止都假设2026-11-09，每个目标copies1、同一synthetic卡池；可达性和无可比战斗收益分开，偏好保留预算、不充值，反转条件是预算或偏好改变。要含不抽方案。三种收入情景各自成功率是多少？不要把同一预算分别完整给两个目标。",
        "damage": "固定状态普通直伤：public_panel属性1000、unit flat、装备再加0，倍率2、额外固定伤害0；攻击方80级、敌80级，增伤0.5、减防0、无视防御0、抗性0.2、穿抗0、易伤0.25、暴击率0.5、暴伤1，crit_mode expected，敌未击破。只把增伤改为1比较单因素收益。给出基准、变体、相对变化，并说明这个数字能否直接当作整场收益。",
        "unknown": "我不知道限定角色池垫了多少抽，也不知道是不是大保底。假设使用 hsr-character-assumed 经验曲线、预算10抽、目标1个。请用工具给可能状态范围，不猜初始状态；顺便明确这个概率是不是官方精确值。如果未来目标卡池日期完全不知道，就不要编日期计算长期保证。",
    }
    run_turn(common+prompts[args.case],args.label or args.case)


if __name__ == "__main__":
    main()
