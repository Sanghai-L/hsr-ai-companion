"""Audit completed evidence, render P1 gate and update requirement ownership."""
from datetime import datetime, timezone, timedelta
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

from record import record, render, snapshot

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / ".local/evidence/D020"


def read(path):
    return json.loads((ROOT / path).read_bytes())


def write(path, value):
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def accepted_host(path, expected):
    data = read(path)
    assert data["exit_code"] == 0 and not data["timeout"], path
    calls = []
    for line in data["stdout"].splitlines():
        item = json.loads(line).get("item", {})
        if item.get("type") == "mcp_tool_call" and item.get("server") == "hsr_companion" and item.get("status") == "completed":
            calls.append(item)
    relevant = [item for item in calls if item.get("tool") == expected]
    assert relevant and all(not item.get("error") for item in relevant), path
    payload = relevant[-1]["result"]["structured_content"]
    assert payload["status"] in {"success", "partial"}
    assert not any(i["tool"] in {"account_import", "account_refresh", "program_update_apply"} for i in calls)
    if expected == "session_bootstrap":
        assert payload["data"]["state"]["default_account_id"] == "synthetic-b"
        assert payload["data"]["state"]["style"] == "B"
        assert payload["data"]["uid_refreshed"] is False and payload["data"]["program_installed"] is False
        assert not payload["missing_fields"]
    thread = next(json.loads(line)["thread_id"] for line in data["stdout"].splitlines() if json.loads(line).get("type") == "thread.started")
    return {"evidence": path, "thread_id": thread, "tool": expected, "completed_tools": [i["tool"] for i in calls],
            "exit_code": data["exit_code"], "uid_refreshed": False}


def main():
    stamp = datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")
    baseline = read("docs/requirements/baseline.json")
    assert hashlib.sha256((ROOT / baseline["prd"]).read_bytes()).hexdigest() == baseline["sha256"]
    assert all(hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest for name, digest in baseline["planning_hashes"].items())
    cases = ET.parse(EVIDENCE / "regression.xml").getroot().findall(".//testcase")
    assert cases and all(case.find("failure") is None and case.find("error") is None and case.find("skipped") is None for case in cases)
    hosts = [accepted_host(".local/evidence/D018/codex-foundation.json", "status"),
             accepted_host(".local/evidence/D020/codex-onboarded.json", "session_bootstrap"),
             accepted_host(".local/evidence/D020/codex-restart.json", "session_bootstrap")]
    assert len({item["thread_id"] for item in hosts}) == 3
    clean = read(".local/evidence/D020/fresh-install-summary.json")
    assert clean["status"] == "PASS" and clean["command_failures"] == 0
    assert clean["knowledge_private_db_unchanged"] and clean["uid_network_requests"] == 0
    assert hashlib.sha256(Path(clean["wheel"]).read_bytes()).hexdigest() == clean["wheel_sha256"]
    p0 = read(".local/evidence/D009/validation-shared.json")
    assert p0["failed"] == 0
    environment = {"python": sys.version, "prefix": sys.prefix,
        "requirements_lock_sha256": hashlib.sha256((ROOT / "requirements.lock").read_bytes()).hexdigest(),
        "packages": {name: importlib.metadata.version(name) for name in (
            "hsr-ai-companion", "jsonschema", "hatchling", "editables", "pytest")}}
    write(".local/evidence/D010/environment.json", environment)
    gate = {"at": stamp, "status": "PASS_USER_ADJUSTED_SCOPE", "host_scope": ["codex"],
        "user_deferred": ["claude-code", "dsh"], "original_three_host_requirement_met": False,
        "version": "0.1.0.dev1", "snapshot": snapshot(), "regression": {"passed": len(cases), "failed": 0, "skipped": 0},
        "clean_install_commands": clean["commands"], "actual_host_sessions": hosts,
        "knowledge_source_validation": "synthetic local maintainer feed; no public production source yet",
        "persistent_codex_project_trust_verified": False, "codex_session_adapter_verified": True,
        "uid_live_requests": 0, "program_update_installed": False, "whole_game_accuracy_verified": False,
        "p0_shared_checks_passed": p0["passed"], "next_task": "D021"}
    write("docs/gates/P1.json", gate)
    text = f'''# P1 基础关口

日期：{stamp}。结论：**PASS_USER_ADJUSTED_SCOPE**。D010～D020 在当前 Codex 范围完成；Claude Code、DSH 延续用户暂缓决定，原三宿主要求未全部通过。

| 验证 | 结果与证据 |
|---|---|
| P1 指定回归 | {len(cases)} 通过，0 失败、0 跳过；`.local/evidence/D020/regression.xml` 与 regression.log |
| 全新安装目录 | 最终 wheel 在新的中文空格目录离线安装；{clean['commands']} 个命令取得预期退出码；fresh-install-commands.json／fresh-install-summary.json |
| 真实 Codex | 3 个独立新会话：基础状态、初始化、重启；后两次自动调用 session_bootstrap，恢复合成 B 账号与风格；原始轨迹仅在 .local |
| 数据与恢复 | 两账号隔离，未知／0 区分，事务回滚、并发写、真实子进程中断恢复、Windows junction 越界拒绝 |
| 知识同步 | 三条原创测试知识；本地维护者新版自动生效，损坏／不兼容不覆盖，旧代恢复；同步前后个人数据库哈希一致 |
| 程序政策 | 只检测并保存指纹／范围绑定方案；无可信确认拒绝、一次性使用、包变化失效；没有安装程序新版 |
| P0 保护 | 原 PRD 和两份规划哈希未变，P0 共享检查 {p0['passed']} 项通过 |

## 本阶段形成的基础

D010 工程与锁定环境；D011 统一结果／错误／来源；D012 形态、单位与版本；D013 私有 SQLite 和不可变 Markdown；D014 数据知识包；D015 原子同步与恢复；D016 程序方案和确认政策；D017 共用 CLI/MCP；D018 当前 Codex 开发安装；D019 初始化、风格、双账号及会话；D020 本关口。

## 与最终产品验收的区别

A01 仅完成同一 Windows 主机的新目录／新虚拟环境开发安装，干净 OS 与正式安装器仍在 D051／D056。A02 仅通过 Codex 的会话参数兼容入口；项目配置模板存在，但持久项目信任流程未验收。A03 完成本地双账号；A06 证明启动／更新不查 UID。A10／A12 完成合成维护者源的自动同步和不兼容拒绝，没有假称已接入正式公网知识源。

A04／A05 的公开 UID 导入、故障合并在 D024；A11 的实际安装／备份／回滚在 D051。研究语义与冲突流程、全文检索、公式、抽卡计划、完整模拟及高精度核验均仍属于后续任务。

## 真实试验中的修复与限制

Codex 初次配置未形成可用 transport；改用完整会话 MCP 参数的安装入口。第二次试验发现标准 tools/list `_meta` 被误拒，已修复并补回归；共同规则直接生成到 AGENTS.md，避免额外 shell 读取。失败记录在 `.local/evidence/D018/codex-foundation.attempt-*.json`。未改全局配置，未给写工具设置免批准；后两次使用宿主原生自动审查。

本机执行沙箱拒绝 Windows 严格真实路径句柄解析，因此需要真实路径／junction 的验证在授权工具执行环境中运行；保留 strict 检查，没有降级成字符串判断。所有路径和资料均为项目临时目录。测试模型请求仅来自显式的实际 Codex 验收，应用本身不调用额外模型。没有真实 UID 查询，没有对外发布。

程序确认信任边界见 [合同](../contracts/updates-and-consent.md)；没有可核验 Codex 业务批准回执时只保留方案，MCP 不接受模型参数充当用户批准。维护者正式签名发布源后续建立，全文索引在 D022 接入同一准备流程。

## 复核入口

按 README 的 P1 指定 pytest 命令回归。原始命令、退出码、测试计数、源码快照、wheel 哈希和宿主会话分别保存在任务账本、P1.json 及 .local/evidence/D010～D020。

下一项是 **D021：建立首批公共机制知识**。本轮未启动 P2。
'''
    (ROOT / "docs/gates/P1.md").write_text(text, encoding="utf-8")
    record("D020", artifacts=["docs/gates/P1.md", "docs/gates/P1.json", "README.md"],
        commands=[".venv/Scripts/python.exe -m pytest tests/smoke tests/contracts tests/domain tests/storage tests/knowledge/test_package.py tests/updates tests/policy tests/transport tests/adapters tests/session -q -ra --basetemp=.local/tmp/pytest-d020-reviewed --junitxml=.local/evidence/D020/regression.xml",
                  ".venv/Scripts/python.exe tools/p1/run_gate.py --output '.local/probes/p1/干净 安装验收 02'",
                  ".venv/Scripts/python.exe tools/p1/verify_codex.py --phase onboarded",
                  ".venv/Scripts/python.exe tools/p1/verify_codex.py --phase restart",
                  ".venv/Scripts/python.exe tools/p0/validate_p0.py --shared-only"],
        evidence=[".local/evidence/D020/regression.xml", ".local/evidence/D020/regression.log",
                  ".local/evidence/D020/fresh-install-commands.json", ".local/evidence/D020/fresh-install-summary.json",
                  ".local/evidence/D020/codex-onboarded.json", ".local/evidence/D020/codex-restart.json"],
        xml=".local/evidence/D020/regression.xml", summary=f"P1 当前 Codex 范围通过：{len(cases)} 测试、22 条干净安装命令、真实新会话与重启；P2 未开始",
        level="离线合同／真实 Windows 新 venv wheel 安装／真实 Codex；合成本地维护者源，非公网 UID 或游戏结果核验")
    ledger = read("docs/development/task-status.json")
    for task in ledger["tasks"][9:20]:
        task["final_verified_at"] = stamp
        task["snapshot"] = gate["snapshot"]
        task["final_regression"] = {"evidence": ".local/evidence/D020/regression.xml", **gate["regression"]}
    d010 = ledger["tasks"][9]
    d010["commands"] = list(dict.fromkeys(["Python312/python.exe -m venv .venv",
        ".venv/Scripts/python.exe -m ensurepip --upgrade --default-pip (project-local TEMP)",
        ".local/tools/uv/uv.exe pip compile requirements.in --python .venv/Scripts/python.exe --generate-hashes --output-file requirements.lock",
        ".local/tools/uv/uv.exe pip sync --python .venv/Scripts/python.exe --require-hashes requirements.lock",
        ".local/tools/uv/uv.exe pip install --python .venv/Scripts/python.exe --no-deps --no-build-isolation -e .",
        ".venv/Scripts/python.exe -m companion --help", *d010["commands"]]))
    d010["evidence"] = list(dict.fromkeys([*d010["evidence"], ".local/evidence/D010/resolve-lock.log", ".local/evidence/D010/install-lock.log", ".local/evidence/D010/environment.json"]))
    assert all(t["status"] == "DONE" for t in ledger["tasks"][:20])
    assert all(t["status"] == "NOT_STARTED" for t in ledger["tasks"][20:])
    write("docs/development/task-status.json", ledger)
    render(ledger)
    print(json.dumps({"status": gate["status"], "tests_passed": len(cases), "fresh_commands": clean["commands"],
                      "actual_host_sessions": len(hosts), "next_task": "D021"}, ensure_ascii=False))


if __name__ == "__main__":
    main()

