"""Bounded real Codex conversations, separate from synthetic tool protocol tests.

Uses installed host authentication and its native approval review. Does not change
global configuration, publish, query player UIDs or call a third-party model.
The memory phase records an actual scripted player reply through an isolated,
out-of-band verifier; that verifier is never installed in the application.
"""
import argparse
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
from companion.contracts import canonical
from companion.memory.revisions import Revisions
from companion.storage import Store
from record import ROOT, now, write_json

WORKSPACE = ROOT / ".local/probes/p2/Codex 中文 空格项目"
DATA = WORKSPACE / ".local/player"
STATE = ROOT / ".local/evidence/D028/host-state.json"


def run_turn(prompt, *, task, label, session_id=None):
    setup = json.loads((ROOT / ".local/evidence/D005/host-setup-status.json").read_bytes())["codex"]["model_selection"]
    evidence = ROOT / f".local/evidence/{task}/codex-{label}.json"
    if evidence.exists():
        raise RuntimeError(f"preserve prior evidence: {evidence}")
    evidence.parent.mkdir(parents=True, exist_ok=True)
    command = [shutil.which("codex"), "exec", "--ignore-user-config", "--skip-git-repo-check", "--json", "-C", str(WORKSPACE),
               "--approve-for-me", "-o", str(evidence.with_suffix(".answer.txt"))]
    if setup.get("model"):
        command += ["--model", setup["model"]]
    overrides = ["web_search=\"disabled\"", *json.loads((WORKSPACE / ".hsr-companion/mcp-overrides.json").read_bytes())]
    if setup.get("model_reasoning_effort"):
        overrides.append("model_reasoning_effort=" + json.dumps(setup["model_reasoning_effort"]))
    for value in overrides:
        command += ["-c", value]
    if session_id:
        command += ["resume", session_id]
    # Passing Unicode and arbitrary user prose through stdin avoids Windows argv encoding/length limits.
    command += ["-"]
    environment = os.environ.copy()
    environment.update(PYTHONUTF8="1", PYTHONIOENCODING="utf-8", TEMP=str(ROOT / ".local/tmp"), TMP=str(ROOT / ".local/tmp"))
    started = time.monotonic()
    process = subprocess.Popen(command, cwd=WORKSPACE, env=environment, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, encoding="utf-8", errors="replace")
    timeout = False
    try:
        stdout, stderr = process.communicate(prompt, timeout=180)
    except subprocess.TimeoutExpired:
        timeout = True
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, timeout=15)
        stdout, stderr = process.communicate(timeout=10)
    events, calls = [], []
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        events.append(event)
        if event.get("type") == "thread.started":
            session_id = event.get("thread_id")
        item = event.get("item", {})
        if item.get("type") == "mcp_tool_call" and item.get("server") == "hsr_companion" and item.get("status") == "completed":
            calls.append(item)
    answer = evidence.with_suffix(".answer.txt").read_text(encoding="utf-8") if evidence.with_suffix(".answer.txt").exists() else ""
    record = {"at": now(), "args": command, "prompt": prompt, "pid": process.pid, "exit_code": process.returncode, "timeout": timeout,
              "seconds": round(time.monotonic()-started,3), "session_id": session_id, "stdout": stdout, "stderr": stderr,
              "completed_tools": [c.get("tool") for c in calls], "answer": answer, "layer": "actual Codex with installed project MCP and skills",
              "global_config_changed": False, "confirmation_adapter": "none; scripted player turns only"}
    record["answer_complete"] = bool(answer.strip()) and any(e.get("type") == "turn.completed" for e in events)
    write_json(evidence, record)
    print(json.dumps({"label": label, "exit_code": process.returncode, "seconds": record["seconds"], "tools": record["completed_tools"],
                      "answer_tail": answer[-1200:], "stderr_tail": stderr[-400:]}, ensure_ascii=False), flush=True)
    if timeout or process.returncode != 0 or not session_id or not record["answer_complete"]:
        raise RuntimeError("host turn did not complete; inspect preserved evidence")
    if any(c.get("tool") == "account_refresh" for c in calls):
        raise RuntimeError("unauthorized UID query attempted by host")
    return session_id, record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=["discussion", "memory", "supplement", "confirm-replay"], required=True)
    args = parser.parse_args()
    install_codex(WORKSPACE, sys.executable, DATA, offline=True)
    if args.phase == "confirm-replay":
        final = json.loads((ROOT / ".local/evidence/D028/host-final-state.json").read_bytes())
        consent = json.loads((ROOT / ".local/evidence/D028/scripted-player-confirmation.json").read_bytes())
        run_turn(f"刚才确认修订后的回复曾因连接中断而没显示完整。请核实并幂等执行同一方案 {final['plan_id']}，expected_id={consent['old_id']}，已有 confirmation_id={consent['confirmation_id']}。沿用这一次确认，不新增替换、不重复询问；核实当前结论和旧历史后简短回显。", task="D028", label="07b-confirm-replay", session_id=final["fresh_session"])
        return
    if args.phase == "supplement":
        final = json.loads((ROOT / ".local/evidence/D028/host-final-state.json").read_bytes())
        run_turn("给 demo-a 补充 10 张星轨专票，这是我明确提供的手工资料；不查询 UID。用现成工具保存并简短回显，不需要查应用源码。", task="D027", label="09-self-contained-fields", session_id=final["fresh_session"])
        return
    if args.phase == "discussion":
        if STATE.exists():
            raise RuntimeError("preserve existing acceptance state")
        session = None
        turns = [
            ("01-onboard-mechanism", "我们先用手工账号 demo-a，选 A，自然聊天；暂不提供 UID，不要查询。按 4.6 说说三月七的存护和巡猎是否同一套技能，简短回答。"),
            ("02-wrong-view", "我觉得强化普攻肯定都恢复战技点，不用查例外吧？"),
            ("03-counterexample-account", "巡猎三月七的强化普攻明确不恢复战技点，这是有效反例。请据此限定具体技能，不要硬反驳我。顺便把 demo-a 的星琼记为 1600，这是我明确提供的手工资料；不导入 UID。"),
        ]
        for label, prompt in turns:
            session, result = run_turn(prompt, task="D027", label=label, session_id=session)
            write_json(STATE, {"discussion_session": session, "last_label": label, "data_dir": str(DATA), "at": now()})
        return
    state = json.loads(STATE.read_bytes())
    session, _ = run_turn("保存一条独立的合成研究结论：测试技能 T 在条件 S 下产 1 个战技点。claim_key=p2-resource-test，实体 synthetic:T，版本 4.6，条件 S。来源是我本条提供的合成设定，不代表真实游戏。作为有条件结论保存到 demo-a 私有研究，不改公共知识。", task="D028", label="04-save", session_id=state["discussion_session"])
    # A genuinely fresh host session must recover from the application's durable memory.
    session, _ = run_turn("继续 demo-a 上次关于合成测试技能 T 的研究，切换为 B 专业分析风格。先找回旧结论和适用条件；不刷新 UID。", task="D028", label="05-fresh-continuation")
    session, _ = run_turn("加入相同条件 S 下的新合成证据：测试记录 https://example.com/p2-synthetic-test 说 T 实际消耗 1 个战技点。以上正文是我提供的手工测试记录，不要联网。请登记它与旧结论的冲突，提出把结论改为条件 S 下消耗 1 点的具体方案，先等我回复，别覆盖旧文。", task="D028", label="06-conflict", session_id=session)
    store = Store(DATA / "personal")
    with store.connection() as connection:
        rows = connection.execute("SELECT * FROM revision_plans WHERE account_id='demo-a' AND state='proposed' ORDER BY rowid DESC").fetchall()
    if not rows:
        raise RuntimeError("host did not propose a revision")
    row = rows[0]
    plan = json.loads(row["payload"])
    old_text = store.read_research("demo-a", plan["expected_id"])
    # Harness receives the exact scripted player reply, independently of all model parameters.
    reply = f"确认方案 {row['id']}：只修改这个合成测试结论，条件 S 下 T 消耗 1 点，保留历史。"
    receipt = {"source_kind": "host_native", "source_ref": "p2-controlled-player-turn:" + uuid.uuid4().hex,
               "reply_text": reply, "decision": "approve", "binding_sha256": row["binding_sha256"]}
    confirmation_id = Revisions(store).record_verified("demo-a", row["id"], receipt,
        verifier=lambda supplied, digest: supplied is receipt and supplied["reply_text"] == reply and digest == row["binding_sha256"])
    write_json(".local/evidence/D028/scripted-player-confirmation.json", {"adapter": "isolated controlled transcript verifier; NOT a native Codex business receipt", "receipt": receipt,
               "confirmation_id": confirmation_id, "old_id": plan["expected_id"], "old_body_sha256": hashlib.sha256(old_text.encode()).hexdigest()})
    session, _ = run_turn(reply + f"\n受控验收的可信玩家回复适配已记录此消息，confirmation_id={confirmation_id}，expected_id={plan['expected_id']}。这是已存在的记录，执行该具体方案即可，不再询问。", task="D028", label="07-confirm-apply", session_id=session)
    session, _ = run_turn("现在请精确模拟未知完整练度的两队在当前最新混沌的最优成绩，并据此计算未来抽卡概率。如果这些能力还没实现，直接说明能确定的部分和缺口，在当前预算内结束，不写计算脚本、不编数字。", task="D028", label="08-budget-unsupported", session_id=session)
    with store.connection() as connection:
        final = connection.execute("SELECT state,result_id FROM revision_plans WHERE id=?", (row["id"],)).fetchone()
        uid_count = connection.execute("SELECT COUNT(*) FROM uid_queries").fetchone()[0]
    assert final["state"] == "applied" and uid_count == 0
    assert store.read_research("demo-a", plan["expected_id"]) == old_text
    write_json(".local/evidence/D028/host-final-state.json", {"revision_applied": True, "history_unchanged": True,
               "uid_query_count": uid_count, "plan_id": row["id"], "new_id": final["result_id"], "discussion_session": state["discussion_session"],
               "fresh_session": session, "current_style": store.require_account("demo-a")["style"], "at": now()})


if __name__ == "__main__":
    main()
