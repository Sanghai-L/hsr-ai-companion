"""Close P2 only from existing, inspected real evidence; never generate passes."""
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from companion import __version__, PROGRAM_API_VERSION
from companion.accounts import AccountService
from companion.contracts import canonical
from companion.knowledge.package import KnowledgePackage, build_package
from companion.storage import Store
from record import ROOT, now, record, snapshot, write_json


def read(relative):
    return json.loads((ROOT / relative).read_bytes())


def envelope(item):
    result = item.get("result") or {}
    if "structured_content" in result:
        return result["structured_content"]
    if "structuredContent" in result:
        return result["structuredContent"]
    for block in result.get("content", []):
        if block.get("type") == "text":
            try:
                return json.loads(block["text"])
            except ValueError:
                pass
    return {}


def host_evidence():
    records = []
    for task in ("D027", "D028"):
        for path in sorted((ROOT / f".local/evidence/{task}").glob("codex-*.json")):
            item = json.loads(path.read_bytes())
            events = []
            for line in item["stdout"].splitlines():
                try:
                    events.append(json.loads(line))
                except ValueError:
                    pass
            calls = [e["item"] for e in events if e.get("item", {}).get("type") == "mcp_tool_call" and e["item"].get("status") == "completed"]
            assert item["exit_code"] == 0 and not item["timeout"]
            assert not any(c.get("tool") == "account_refresh" for c in calls)
            assert all(envelope(c).get("status") in {"success", "partial"} for c in calls), path
            records.append({"evidence": path.relative_to(ROOT).as_posix(), "session_id": item["session_id"],
                            "answer_complete": bool(item["answer"].strip()), "seconds": item["seconds"],
                            "tools": [c.get("tool") for c in calls]})
    missing = [r for r in records if not r["answer_complete"]]
    assert len(missing) == 1 and missing[0]["evidence"].endswith("codex-07-confirm-apply.json")
    replay = next(r for r in records if r["evidence"].endswith("codex-07b-confirm-replay.json"))
    assert replay["answer_complete"] and "memory_revision_apply" in replay["tools"]
    supplement = next(r for r in records if r["evidence"].endswith("codex-09-self-contained-fields.json"))
    assert supplement["tools"] == ["account_get", "account_patch"]
    return records


def main():
    cases = ET.parse(ROOT / ".local/evidence/D028/regression-final.xml").getroot().findall(".//testcase")
    assert len(cases) == 109
    assert all(c.find("failure") is None and c.find("error") is None and c.find("skipped") is None for c in cases)
    live = ET.parse(ROOT / ".local/evidence/D024/live.xml").getroot().findall(".//testcase")
    assert len(live) == 1 and live[0].find("failure") is None and live[0].find("error") is None
    install = read(".local/evidence/D028/fresh-install-summary.json")
    assert install["state"] == "PASS" and install["commands"] == 25 and install["failures"] == 0
    wheel = Path(install["wheel"])
    assert __version__ in wheel.name and hashlib.sha256(wheel.read_bytes()).hexdigest() == install["wheel_sha256"]
    content = build_package(ROOT / "knowledge", version="0.2.0")
    assert KnowledgePackage.decode((ROOT / "src/companion/resources/knowledge/bundle.json").read_bytes()).fingerprint == content.fingerprint
    assert content.compatible(PROGRAM_API_VERSION) and not content.compatible("0.1.0")
    retrieval = read(".local/evidence/D022/retrieval.json")["results"]
    validation = [r for r in retrieval if r["split"] == "validation"]
    assert len(validation) == 12 and all(r["hit"] for r in validation)
    query_path = ROOT / "evals/retrieval/queries.json"
    assert hashlib.sha256(query_path.read_bytes()).hexdigest() == (query_path.with_suffix(".sha256").read_text().strip())
    hosts = host_evidence()
    store = Store(ROOT / ".local/probes/p2/Codex 中文 空格项目/.local/player/personal", read_only=True)
    account = AccountService(store).get("demo-a")
    fields = {f["field_id"]: f for f in account["snapshot"]["fields"]}
    assert fields["stellar_jade"]["quantity"]["value"] == 1600 and fields["star_rail_special_pass"]["quantity"]["value"] == 10
    assert all(f["source"]["type"] == "manual" for f in fields.values()) and account["account"]["style"] == "B"
    final = read(".local/evidence/D028/host-final-state.json")
    with store.connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM uid_queries").fetchone()[0] == 0
        plan = connection.execute("SELECT * FROM revision_plans WHERE id=?", (final["plan_id"],)).fetchone()
        assert plan["state"] == "applied" and plan["confirmation"] and plan["result_id"] == final["new_id"]
        root_id = json.loads(plan["payload"])["root_id"]
        head = connection.execute("SELECT revision,current_id FROM memory_heads WHERE account_id='demo-a' AND root_id=?", (root_id,)).fetchone()
        assert head["revision"] == 2 and head["current_id"] == final["new_id"]
    consent = read(".local/evidence/D028/scripted-player-confirmation.json")
    old = store.read_research("demo-a", consent["old_id"])
    assert hashlib.sha256(old.encode()).hexdigest() == consent["old_body_sha256"]
    review = {"reviewer": "primary agent, direct review of real answers and tool/state traces", "scope": "controlled Codex acceptance, not a claim of native business receipts",
              "mechanism_and_counterexample": ".local/evidence/D027/semantic-review.json",
              "fresh_recovery": {"passed": True, "evidence": "codex-05-fresh-continuation.json", "observed": "retrieves synthetic T condition S, 4.6 and original source; style B persisted"},
              "conflict": {"passed": True, "evidence": "codex-06-conflict.json", "observed": "manual evidence accurately distinguished from fetched web page; old text preserved; exact plan awaiting reply"},
              "revision": {"passed": True, "evidence": ["codex-07-confirm-apply.json", "codex-07b-confirm-replay.json"], "observed": "business commit succeeded before model connection interruption; same trusted confirmation replays with idempotent=true, no duplicate replacement; current and old history verified"},
              "unsupported_and_budget": {"passed": True, "evidence": "codex-08-budget-unsupported.json", "observed": "states missing formula/pull/sim tools and missing inputs; no fabricated numerical result, no persistent script; stops after six business tool calls in 85.875 seconds"},
              "self_contained_account_contract": {"passed": True, "evidence": "codex-09-self-contained-fields.json", "observed": "only account_get and account_patch; manual tickets 10; zero shell commands and no UID query"},
              "host_records": hosts, "failed_attempt_preserved": "first turn-07 final answer empty after network disconnect; not counted as a complete answer", "semantic_sample_size_limit": "small controlled script; broad quality evaluation remains D054"}
    write_json(".local/evidence/D028/semantic-review.json", review)
    summary = {"at": now(), "status": "PASS_CURRENT_CODEX_SCOPE_WITH_LIMITATIONS", "program": __version__, "program_api": PROGRAM_API_VERSION,
               "snapshot": snapshot(), "tasks": [f"D{i:03}" for i in range(21,29)], "host_scope": {"codex": "passed controlled actual conversations", "claude_code": "deferred by user", "dsh": "deferred by user"},
               "regression": {"passed": 109, "failed": 0, "skipped": 0, "evidence": ".local/evidence/D028/regression-final.xml"},
               "public_uid": {"passed": 1, "requests": 1, "evidence": ".local/evidence/D024/uid-live.json", "private_player_account_queried": False},
               "knowledge": {"entries": 32, "version": "0.2.0", "sha256": content.fingerprint, "minimum_program": "0.1.1", "validation_queries": 12, "top5_hits": 12, "dataset": "p2-retrieval-1"},
               "installation": install, "actual_host_turns": len(hosts), "actual_host_sessions": len({r["session_id"] for r in hosts}),
               "host_uid_queries": 0, "confirmation_adapter": "isolated actual scripted player turn verifier; native Codex adapter unavailable; product offers interactive terminal confirmation",
               "original_docs_check": {"command": "python -X utf8 tools/p0/validate_p0.py --shared-only", "exit_code": 0, "checks": 37},
               "not_published": True, "next_task": "D029", "evidence": [".local/evidence/D028/semantic-review.json", ".local/evidence/D028/host-final-state.json", ".local/evidence/D028/fresh-install-summary.json"]}
    write_json("docs/gates/P2.json", summary)
    report = f'''# P2 研究与记忆关口

日期：2026-11-08。结论：**PASS_CURRENT_CODEX_SCOPE_WITH_LIMITATIONS**。D021～D028 在用户保留的 Codex 范围完成；Claude Code、DSH 继续暂缓，没有宣称三端全部通过。

| 验证层次 | 实际结果与证据 |
|---|---|
| 完整离线回归 | **109 通过，0 失败、0 跳过**；.local/evidence/D028/regression-final.xml |
| 公共知识与检索 | 32 条原创来源知识；42 个固定人工查询，30 个开发、12 个保留验证；验证集 Top-5 **12/12，100%**；评测集未改标签 |
| 正式资料连接器 | 实际 HTTPS 获取锁定公开文档；过期、失效、超时、429、格式变化和转载冲突另由离线样本验证 |
| 公开 UID | **1 次**文档作者公开样例导入，实际核对角色 ID、形态、等级、晋阶和星魂；原响应仅 .local/evidence/D024；未查用户私人账号 |
| 真实 Codex | **2 个独立会话、10 个回合记录**；其中原第 7 回合业务提交后连接中断、回显不完整，单列保留；07b 用原确认成功幂等重放。错误观点、有效反例、A/B、手工资料、新会话接续与预算停止已审阅 |
| 干净安装 | 最终 {__version__} wheel 在新中文空格路径／新 venv 离线安装，**25 条命令**全部取得预期退出码；fresh-install-summary.json 与 commands.json |
| 数据边界 | 两账号隔离、v1→v2 迁移、手工优先、TTL 不刷新、并发旧快照拒绝、长研究分页、正文恢复、冲突未答复与历史保留、重复修订幂等通过 |
| 旧基线保护 | 原 PRD 和两份规划未改；P0 共享验证 **37 项通过** |

## 已交付

D021 三类首批知识与来源登记；D022 中文词项／字符索引、别名与形态消歧、版本／正式服过滤、来源分页和索引重建；D023 证据、转载依赖、带日期缓存与来源冲突；D024 公开 UID 正式连接器、动作记录、原响应／标准化／手工覆盖分层、差异和预期版本修订；D025 分类记忆、跨会话检索与上下文预算；D026 绑定具体方案的确认、替换／限缩／废止与历史；D027 三个共用技能、A/B 和宿主规则；D028 本关口。

当前软件为 {__version__}，程序 API 0.1.1；知识为 0.2.0。扩展知识含新类别与来源论点字段，最低程序版本已明确为 0.1.1。最后版本修正没有改检索标签、知识正文或修订语义；最终 109 项回归与最终 wheel 安装覆盖该修正。真实对话主体在此前 0.1.0.dev2 实现上完成，证据保留原轨迹。

## 必须保留的边界

1. 当前 Codex **没有原生业务回复回执连接器**。产品交付本地交互 confirm-revision，展示具体方案并记录一次玩家确认；受控宿主验收的脚本玩家回复适配不安装到产品，不能据此宣称普通 Codex 对话自动确认已完成。同一已记录方案的确认可直接沿用。
2. 32 条知识和 12 个验证查询是工程起始规模；正文核对不等于完整游戏内交互精度。其他区服与完整角色覆盖、当前卡池和关卡时效仍须按问题核验。测试来源不是正式公网维护者发布源。
3. 装备实例 ID 只代表展示观察；未展示不代表未持有，完整背包、星琼与保底没有被读取。字段日期与手工冲突保留，不能把老观察当完整实时库存。
4. 研究预算目前由共用规则约束，实际宿主测试另有墙钟超时；全局强制计算预算与取消／恢复属于 D039／D053。语义评测是有限脚本，全面质量验收仍在 D054。
5. 现阶段无正式公式、抽卡规划和完整战斗模拟；本地可行性结果不能充作玩家配队或抽卡建议。正式安装器、干净 Windows、签名发布、完整安全演练和总项目许可证仍由后续任务处理。

## 实际试验中的改进

手工补充的初版工具 schema 只写 object，真实 Agent 为获知字段而读取源码；已改成完整内联字段合同，09 复测只调用 account_get／account_patch，保存 10 张星轨专票且没有 shell 调用。第 7 回合模型连接中断没有破坏事务；07b 返回 idempotent=true，当前指针只增加一次、旧原文指纹不变。失败轨迹未删除，也没有算成完整回答。

正文和元信息的效力以当前指针／修订状态为准；受控样例的拟修订正文包含待确认措辞，确认后的实际有效状态和结论已由工具及回显核对，广泛文本质量评测仍留 D054。公共源未观察到玩家写入，全部真实 UID／宿主原始轨迹保存在 .local。

详细脚本见 evals/scripts/research-session.md；合同见 docs/contracts/accounts.md、memory.md、source-resolution.md、research-workflow.md。验证命令、源码快照、构建哈希、阶段状态见 P2.json 和 docs/development/task-status.json。

下一项是 **D029：定义实验和方案比较合同**，属于 P3，本轮没有开始。没有对外发布。
'''
    (ROOT / "docs/gates/P2.md").write_text(report, encoding="utf-8")
    trace = ROOT / "docs/requirements/traceability.md"
    text = trace.read_text(encoding="utf-8")
    text = text.replace("P2 进行中：D021 已完成 32 条有定位、版本及限制的来源知识；见 knowledge/sources.json 和 .local/evidence/D021/tests.xml。A13/A14 的完整时效与隔离仍需后续来源／检索验收。", "")
    text += '''\n## P2 本地完成证据（2026-11-08）

| 验收项 | 本轮实际证据与最终验收边界 |
|---|---|
| A03～A06 | 正式公开 UID 导入、部分展示、缺字段、关闭／空展示、429、超时、格式变化、TTL、手工冲突、二账号和并发保护；一次文档公开样例实测；真实宿主全过程 UID 查询为 0 |
| A07 | 分类追加、条件／版本检索与上下文预算；新真实 Codex 会话找回合成研究；假设不修改账号事实 |
| A08 | 新证据冲突、具体方案与可信回复、修订历史和幂等通过；原生 Codex 业务回执尚缺，产品提供本地交互确认，受控验证不冒充原生能力 |
| A09、A23 | 公共知识只读工具；网页仅为资料，转载依赖／冲突保留；完整攻击面安全关口仍在 D052 |
| A10、A12 | 全文索引随包准备，可重建；扩展包明确要求程序 0.1.1，不触发程序自动更新 |
| A13、A14 | 32 条知识的具体论点、固定来源 SHA 与版本；正式／beta／leak 隔离，缓存保留日期；当前关卡与卡池时效仍由后续数据层和实际研究核验 |
| A15、A16 | 真实 Codex 错误观点、有效反例、A→B、跨会话及预算停止观察通过；全面语义验收仍在 D054 |
| A17～A22 | 正式公式、抽卡规划和完整战斗模拟未在 P2 实现，明确不可用，没有用近似数字伪装完成 |
| A24 | 共享内容原创／合成，真实响应与对话仅 .local；本轮没有发布，正式分发扫描仍由 D055／D057 完成 |

P2 关口：docs/gates/P2.md；109 项回归、1 次真实公开 UID、25 条最终 wheel 安装命令，原始日志见 .local/evidence/D024、D027、D028。下一项 D029，P3 尚未开始。
'''
    trace.write_text(text, encoding="utf-8")
    matrix = ROOT / "docs/compatibility/agent-matrix.md"
    matrix.write_text(matrix.read_text(encoding="utf-8") + "\n## P2 补充（2026-11-08）\n\nCodex 完成两独立会话的受控多轮研究、个人记忆和冲突修订；回显中断后同确认幂等重放通过。项目技能加载已观察，最终完整字段工具合同手工补充只调用账号工具。原生业务确认回执缺失，提供本地交互路径；测试回复适配只存在隔离脚本。Claude Code、DSH 继续暂缓，仅有共用规则模板。完整证据与限制见 docs/gates/P2.md。\n", encoding="utf-8")
    artifacts = ["docs/gates/P2.md", "docs/gates/P2.json", "evals/scripts/research-session.md", "tools/p2/verify_codex.py", "tools/p2/fresh_install.py", "docs/decisions/ADR-004-p2-research-memory.md"]
    evidence = [".local/evidence/D028/regression-final.xml", ".local/evidence/D024/live.xml", ".local/evidence/D028/semantic-review.json", ".local/evidence/D028/host-final-state.json", ".local/evidence/D028/fresh-install-summary.json", ".local/evidence/D028/fresh-install-commands.json"]
    record("D028", status="DONE", summary="当前 Codex 范围 P2 通过：109 项离线回归、12/12 检索、1 次真实公开 UID、25 条最终安装命令；真实跨会话及修订重放通过，原生确认回执限制明示", artifacts=artifacts, evidence=evidence,
           commands=["python -m pytest tests/smoke tests/contracts tests/domain tests/storage tests/knowledge tests/updates tests/policy tests/transport tests/adapters tests/session tests/sources tests/accounts tests/memory -q -ra --junitxml=.local/evidence/D028/regression-final.xml", "python tools/p2/verify_codex.py --phase memory", "python tools/p2/verify_codex.py --phase confirm-replay", "python tools/p2/verify_codex.py --phase supplement", "python tools/p2/fresh_install.py", "python -X utf8 tools/p0/validate_p0.py --shared-only"], xml=".local/evidence/D028/regression-final.xml", level="离线合同／真实 Windows 新环境 wheel／真实公开 UID／真实 Codex 受控多轮；非三端或游戏准确性认证")
    print(json.dumps({"status": summary["status"], "program": __version__, "passed": len(cases), "top5": "12/12", "wheel_commands": 25, "host_turn_records": len(hosts), "next": "D029"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
