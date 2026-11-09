"""Bounded actual Codex conversations using the installed wheel and synthetic data."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid

from companion.adapters.codex import install_codex

ROOT = Path(__file__).resolve().parents[2]
CASES = ("alpha", "recovery", "pf", "as", "aa")
ACCOUNT = "p5-host-demo"


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def prepare():
    label = uuid.uuid4().hex[:10]
    evidence = ROOT / ".local/evidence/D049" / ("host-" + label)
    workspace = ROOT / ".local/probes/p5-host" / label / "Codex 中文 空格项目"
    data = workspace / ".local/player"
    summary = json.loads((ROOT / ".local/evidence/D049/fresh-480b95e76c/summary.json").read_bytes())
    python = Path(summary["target"]) / "运行 环境/Scripts/python.exe"
    assert python.is_file() and summary["status"] == "PASS"
    wheel = Path(summary["wheel"])
    assert hashlib.sha256(wheel.read_bytes()).hexdigest() == summary["wheel_sha256"]
    # Installer sources are byte-identical to the previously verified installed wheel.
    import zipfile
    with zipfile.ZipFile(wheel) as archive:
        for file in (ROOT / "src/companion").rglob("*.py"):
            assert archive.read("companion/" + file.relative_to(ROOT/"src/companion").as_posix()) == file.read_bytes()
    workspace.mkdir(parents=True)
    install_codex(workspace, python, data, offline=True)
    config = subprocess.run([str(python), "-X", "utf8", "-m", "companion", "--data-dir", str(data), "--offline", "call", "account_configure", "--input", "-"],
        input=json.dumps({"account_id": ACCOUNT, "style": "A", "region": "ASIA"}), capture_output=True, text=True, encoding="utf-8", timeout=30)
    if config.returncode:
        raise RuntimeError("Synthetic account setup failed: " + config.stderr)
    # The player supplies this test document. It is not application source or a private prior trace.
    roster = json.loads((ROOT / "evals/cases/multi-team.json").read_bytes())
    write(workspace / "玩家提供的候选清单.json", roster)
    setup = json.loads((ROOT/".local/evidence/D005/host-setup-status.json").read_bytes())["codex"]["model_selection"]
    plan = {"at": now(), "authorization": "2026-11-08 user replied 允许 to actual isolated Codex acceptance with model usage",
            "workspace": str(workspace), "data_dir": str(data), "python": str(python),
            "codex": shutil.which("codex"), "model_selection": setup,
            "wheel": str(wheel), "wheel_sha256": summary["wheel_sha256"], "evidence": str(evidence),
            "cases": list(CASES), "max_seconds_per_case": 360, "automatic_model_retries": 0,
            "account_setup": json.loads(config.stdout)}
    write(evidence / "plan.json", plan)
    print(json.dumps({"plan": str(evidence/"plan.json"), "workspace": str(workspace), "model": setup.get("model"), "cases": list(CASES)}, ensure_ascii=False))


def prompt(case):
    common = ("这是获授权的星穹铁道助手合成验收。账号p5-host-demo，风格A、区服ASIA；UID先不提供，也不导入或刷新。"
              "用已安装的助手工具完成，不读取应用源码、开发目录或之前的验收轨迹，不写计算脚本；可以读取我在当前项目提供的输入文档和已安装项目技能。"
              "所有内置代表性例子的面板、E0且无大行迹、动作顺序、外部血线及击破状态均是我本次明确接受的工程假设，绝不是我的持有或真实练度。"
              "沿用工具返回的游戏4.6和数据／方法版本。保持简短但要保留会影响结论的条件；不能把输出容量说成分数、必胜或抽卡账号收益。"
              "本题最多12次资料／分析调用、180秒；初始化、合同发现、实验保存及记忆登记另计。\n")
    questions = {
        "alpha": "我想比较混沌回忆里的单体和对群选择。请使用工具内置的混沌代表性例子：单目标、200AV、初始SP3、初始能量0，比较丹恒队和黑塔队。实际计算双方的期望输出及SP／能量收支，解释结论为什么仅在这些假设下成立。请保存这次实验，并把带实验号和明确条件的结论追加到私人研究，主题p5-acceptance、标题P5混沌窗口选择；方便我下个新会话找回后重算。不要提前告诉下个会话任何实验号。",
        "recovery": "这是一个新会话。我忘了之前比较混沌队伍的实验号。请从我的私人研究找回主题p5-acceptance、标题P5混沌窗口选择的记录，读取原条件和实验引用，按保存的输入从头重算，确认结果是否一致。不要用新建示例代替原实验，也不要修改原研究结论。告诉我之前结论和局限。",
        "pf": "虚构叙事里该选单体还是黑塔对群？请用工具内置虚构代表性例子做一次比较。我接受5个持续目标和两次外部跨50%血线机会是假设，不能倒推真实击杀。然后分别把目标数设成1、3、5逐项复算，指出推荐在哪些已测条件下反转，不猜连续阈值。另用工具检查一个缺资料情况：把同一示例里黑塔位置替换为编号99999、形态99999:base的测试占位角色，它不在已验证清单、倍率未知；保留其他输入，能否给这支队伍数值排名？本题不要修改之前的混沌研究。",
        "as": "末日幻影怎么处理击破窗口？请用工具内置末日代表性例子比较丹恒和黑塔配置，保留其击破前后两个外部窗口，核对每个窗口的输出、弱点匹配削韧容量及SP／能量准备。解释哪些是定量结果、哪些还只是操作方向，并说明为何不能预测精确得分。不要修改之前的混沌研究。",
        "aa": "异相仲裁要三队，我担心骑士之间占用相同角色或装备。先使用工具内置异相代表性例子比较一个骑士的配置，说明数值和未量化特性的界限。再读取当前项目的《玩家提供的候选清单.json》：我明确接受其中12名角色可用、无装备触发等假设；请在给出的候选集里用助手工具分配三骑士，检查角色／形态／装备实例，并说明王棋能否复用骑士资源。只推荐这个候选集，不声称全局最优或王棋必胜。本题不要修改之前的混沌研究。",
    }
    return common + questions[case]


def extract_envelope(item):
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


def run(plan_file, case, label=None):
    plan = json.loads(plan_file.read_bytes())
    workspace, evidence = Path(plan["workspace"]), Path(plan["evidence"])
    if not workspace.resolve().is_relative_to((ROOT/".local/probes/p5-host").resolve()):
        raise ValueError("Host test workspace is outside its isolated root")
    label = label or case
    if not label.replace("-", "").replace("_", "").isalnum():
        raise ValueError("Invalid evidence label")
    record_path = evidence / (label + ".json")
    if record_path.exists() or record_path.with_suffix(".stdout.jsonl").exists():
        raise FileExistsError("Preserve previous model evidence")
    selection = plan["model_selection"]
    command = [plan["codex"], "exec", "--ignore-user-config", "--skip-git-repo-check", "--json", "-C", str(workspace),
               "--approve-for-me", "-o", str(record_path.with_suffix(".answer.txt"))]
    if selection.get("model"):
        command += ["--model", selection["model"]]
    overrides = ['web_search="disabled"', *json.loads((workspace/".hsr-companion/mcp-overrides.json").read_bytes())]
    if selection.get("model_reasoning_effort"):
        overrides.append("model_reasoning_effort=" + json.dumps(selection["model_reasoning_effort"]))
    for override in overrides:
        command += ["-c", override]
    command.append("-")
    environment = os.environ.copy()
    temporary = workspace/".local/tmp"
    temporary.mkdir(parents=True, exist_ok=True)
    environment.update(PYTHONUTF8="1", PYTHONIOENCODING="utf-8", TEMP=str(temporary), TMP=str(temporary))
    environment.pop("PYTHONPATH", None)
    started = time.monotonic()
    raw_stdout = record_path.with_suffix(".stdout.jsonl")
    raw_stderr = record_path.with_suffix(".stderr.txt")
    timed_out = False
    with raw_stdout.open("wb") as stdout, raw_stderr.open("wb") as stderr:
        process = subprocess.Popen(command, cwd=workspace, env=environment, stdin=subprocess.PIPE, stdout=stdout, stderr=stderr,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        process.stdin.write(prompt(case).encode("utf-8"))
        process.stdin.close()
        print(json.dumps({"case": case, "state": "running", "pid": process.pid, "evidence": str(record_path)}, ensure_ascii=False), flush=True)
        seen = 0
        while process.poll() is None:
            if time.monotonic()-started > plan["max_seconds_per_case"]:
                timed_out = True
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, timeout=20)
                else:
                    process.terminate()
                process.wait(timeout=20)
                break
            lines = raw_stdout.read_text(encoding="utf-8", errors="replace").splitlines()
            for line in lines[seen:]:
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                item = event.get("item", {})
                if item.get("type") == "mcp_tool_call" and item.get("status") == "completed":
                    print(json.dumps({"case": case, "tool": item.get("tool")}, ensure_ascii=False), flush=True)
            seen = len(lines)
            time.sleep(.5)
    events = []
    for line in raw_stdout.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            events.append(json.loads(line))
        except ValueError:
            pass
    calls = [event["item"] for event in events if event.get("item", {}).get("type") == "mcp_tool_call" and event["item"].get("status") == "completed"]
    answer_file = record_path.with_suffix(".answer.txt")
    answer = answer_file.read_text(encoding="utf-8") if answer_file.exists() else ""
    record = {"at": now(), "case": case, "command": command, "prompt": prompt(case), "exit_code": process.returncode,
              "timeout": timed_out, "seconds": round(time.monotonic()-started, 3), "answer": answer,
              "session_id": next((event.get("thread_id") for event in events if event.get("type") == "thread.started"), None),
              "tools": [{"name": call.get("tool"), "arguments": call.get("arguments"), "envelope": extract_envelope(call)} for call in calls],
              "usage": [event.get("usage") for event in events if event.get("type") == "turn.completed"],
              "raw_stdout": str(raw_stdout), "raw_stderr": str(raw_stderr), "plan": str(plan_file),
              "layer": "actual installed Codex and verified wheel MCP; actual model responses, synthetic player only"}
    write(record_path, record)
    print(json.dumps({"case": case, "exit_code": process.returncode, "timeout": timed_out, "seconds": record["seconds"],
                      "session_id": record["session_id"], "tools": [call["name"] for call in record["tools"]],
                      "answer": answer[:1800], "record": str(record_path)}, ensure_ascii=False), flush=True)
    assert not timed_out and process.returncode == 0 and answer.strip(), "Actual host execution failed; inspect preserved evidence"
    assert not any("account_refresh" in str(call["name"]) for call in record["tools"]), "Unexpected UID operation"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--case", choices=CASES)
    parser.add_argument("--label")
    args = parser.parse_args()
    if args.prepare:
        prepare()
    else:
        if args.plan is None or args.case is None:
            parser.error("--plan and --case required")
        run(args.plan.resolve(), args.case, args.label)


if __name__ == "__main__":
    main()
