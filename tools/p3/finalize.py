"""P3 closes only on inspected real tests, wheel and actual host transcripts."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from companion import __version__, PROGRAM_API_VERSION
from companion.contracts import canonical
from companion.experiments.service import execute
from companion.services.context import Context
from companion.services.registry import Registry
from companion.storage import Store
from record import ROOT, now, record, snapshot, write_json


def read(path):
    return json.loads((ROOT/path).read_bytes())


def completed_shells(host):
    commands = []
    for line in host["stdout"].splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        item = event.get("item",{})
        if event.get("type") == "item.completed" and item.get("type") == "command_execution":
            commands.append(item.get("command", ""))
    return commands


def main():
    origin = ".local/evidence/D034/regression-delivery.xml"
    cases = ET.parse(ROOT/origin).getroot().findall(".//testcase")
    assert len(cases) >= 188 and all(c.find("failure") is None and c.find("error") is None and c.find("skipped") is None for c in cases)
    simulator = ET.parse(ROOT/".local/evidence/D034/simulator-budget.xml").getroot().findall(".//testcase")
    assert len(simulator) == 3 and all(c.find("failure") is None and c.find("error") is None and c.find("skipped") is None for c in simulator)
    install = read(".local/evidence/D034/fresh-install-summary.json")
    assert install["status"] == "PASS" and install["commands"] == 21 and install["failed"] == 0
    assert hashlib.sha256(Path(install["wheel"]).read_bytes()).hexdigest() == install["wheel_sha256"]
    backend = read(".local/evidence/D030/backend-crosscheck.json")
    assert backend["status"] == "PASS" and len(backend["samples"]) == 8
    assert len(read("benchmarks/formulas/sources.lock.json")["sources"]) == 7
    labels = ("timeline", "pulls", "damage", "unknown", "timeline-self-contained", "pulls-self-contained")
    hosts = {label:read(f".local/evidence/D034/codex-{label}.json") for label in labels}
    replay_records = []
    registry = Registry(Context(ROOT/".local/evidence/D034/replay-not-initialized",offline=True))
    for label, host in hosts.items():
        assert host["exit_code"] == 0 and not host["timeout"] and host["answer"].strip() and host["session_id"]
        assert not any(tool["name"] == "account_refresh" for tool in host["tools"])
        for tool in host["tools"]:
            if tool["name"] not in {"calculate", "plan_pulls", "experiment_compare", "calculation_schema"}:
                continue
            assert tool["envelope"]["status"] in {"success","partial"}, (label,tool)
            replay = registry.invoke(tool["name"],tool["arguments"]).to_dict()
            assert replay["status"] == tool["envelope"]["status"], (label,tool)
            assert replay["data"] == tool["envelope"]["data"], (label,tool["name"])
            replay_records.append({"label":label,"tool":tool["name"],"same_data":True,"status":replay["status"],
                                   "experiment_fingerprint":replay["data"].get("experiment_fingerprint")})
    for label, expected in (("timeline-self-contained","calculate"),("pulls-self-contained","plan_pulls")):
        host = hosts[label]
        assert any(t["name"] == expected for t in host["tools"])
        assert any(t["name"] == "calculation_schema" for t in host["tools"])
        normalized_shells = [re.sub(r"[\\/]+", "/", command) for command in completed_shells(host)]
        assert all(".agents/skills/" in command and "/Starrail/schemas" not in command
                   for command in normalized_shells), (label,completed_shells(host))
    timeline_call = next(t for t in hosts["timeline-self-contained"]["tools"] if t["name"] == "calculate")
    timeline = timeline_call["envelope"]["data"]["result"]
    assert [e["at"] for e in timeline["events"] if e["kind"]=="basic"] == [75,125,175]
    assert timeline["sp"] == 3 and timeline["energy"] == {"A":60}
    plan_call = next(t for t in hosts["pulls-self-contained"]["tools"] if t["name"] == "plan_pulls")
    options = plan_call["envelope"]["data"]["result"]["options"]
    probs = [[o["scenarios"][s]["all_targets_probability"] for s in ("conservative","neutral","optimistic")]
             for o in options if o["category"] != "do_not_pull"]
    assert [.5,1,1] in probs and [0,.25,.75] in probs and any(o["category"]=="do_not_pull" for o in options)
    unknown = next(t for t in hosts["unknown"]["tools"] if t["name"] == "calculate")["envelope"]
    assert unknown["status"] == "partial" and unknown["data"]["result"]["state_unknown"]
    assert "官方精确" in hosts["unknown"]["answer"] and "未知" in hosts["unknown"]["answer"]
    store = Store(ROOT/".local/probes/p3/Codex 中文 空格项目/.local/player/personal",read_only=True)
    with store.connection() as connection:
        uid_count = connection.execute("SELECT COUNT(*) FROM uid_queries").fetchone()[0]
    assert uid_count == 0
    write_json(".local/evidence/D034/tool-replay.json",{"at":now(),"records":replay_records,"status":"PASS", "scope":"recompute actual host arguments using final implementation; exact numeric data equality"})
    semantic = {"reviewer":"primary agent, direct inspection of actual answers, arguments and tool results", "at":now(),
        "timeline":{"evidence":"codex-timeline-self-contained.json","passed":True,"observed":"75/125/175, SP3, energy60; local-only and progress preservation stated"},
        "pulls":{"evidence":"codex-pulls-self-contained.json","passed":True,"observed":"single 50/100/100%, sequential double 0/25/75%, shared income once, skip and reversal conditions, no account-benefit percentage ranking"},
        "damage":{"evidence":"codex-damage.json","passed":True,"observed":"2025->2700, 33.33% fixed-state only, same conditions and single changed factor"},
        "unknown":{"evidence":"codex-unknown.json","passed":True,"observed":"possible state bounds, no invented pity or prior, non-official soft-pity explicitly labelled, no future banner date fabricated"},
        "first_round_limitation":"timeline/pull numeric answers passed but host searched development schemas; preserved as diagnosis, explicit installed calculation_schema and examples added and both cases repeated",
        "self_contained_final":{"passed":True,"observed":"both final cases use calculation_schema then quantitative tool; shell only reads installed project skills, no application source/schema files"},
        "semantic_scope":"finite scripted synthetic A-style Codex cases; not general language-quality or game-client certification",
        "host_summary":[{"label":label,"session_id":h["session_id"],"seconds":h["seconds"],"tools":[t["name"] for t in h["tools"]],"completed_shell_commands":len(completed_shells(h))} for label,h in hosts.items()]}
    write_json(".local/evidence/D034/semantic-review.json",semantic)
    state = {"at":now(),"status":"PASS_CURRENT_CODEX_SCOPE_WITH_LIMITATIONS","program":__version__,"program_api":PROGRAM_API_VERSION,"rules":"p3-1", "snapshot":snapshot(),
        "tasks":[f"D{i:03}" for i in range(29,35)],"host_scope":{"codex":"actual conversations passed","claude_code":"deferred by user","dsh":"deferred by user"},
        "core_regression":{"passed":len(cases),"failed":0,"skipped":0,"deselected_live":1,"evidence":origin},
        "isolated_simulator_budget":{"passed":3,"failed":0,"skipped":0,"evidence":".local/evidence/D034/simulator-budget.xml"},
        "source_crosscheck":{"backend_expression_cases":8,"source_records":7,"game_client_accuracy_verified":False},
        "installation":install,"actual_host_sessions":len({h["session_id"] for h in hosts.values()}),"actual_host_turns":len(hosts),"uid_queries":uid_count,
        "preserved_initial_attempts":"initial numeric success with schema-file lookup kept separately; final self-contained repetitions pass",
        "original_document_validation":{"checks":37,"passed":True,"validator_fix":"scope owner uniqueness to primary registry, preserve all 24 owners; historical stage mentions are valid"},
        "not_published":True,"next_task":"D035","limits":["fixed-state ordinary direct damage only","local timeline without enemies or special mechanisms","per-pull curves are assumptions","full battle simulation belongs to P4","finite controlled Codex evaluation only"]}
    write_json("docs/gates/P3.json",state)
    report = f'''# P3 定量分析关口

日期：2026-11-08。结论：**PASS_CURRENT_CODEX_SCOPE_WITH_LIMITATIONS**。D029～D034 在用户保留的 Codex 范围完成；Claude Code、DSH 继续暂缓。

| 层次 | 实际证据 |
|---|---|
| 核心离线回归 | **{len(cases)}通过，0失败、0跳过**；1项 UID live 明确未选择，没有再次查询公开或私人账号；regression-delivery.xml |
| 隔离模拟器预算回归 | 原 P0 后端环境 **3通过**，未把模拟依赖安装到主应用；simulator-budget.xml |
| 独立数学基准 | 普通直伤各乘区、变速剩余距离、概率树穷举及连续目标预算卷积；benchmarks/formulas 与 evals/cases/pull-plans.json |
| 外部表达式核对 | 锁定后端实际执行 **8组**普通伤害乘区；7条来源记录；这不是客户端精度校准 |
| 真实 Codex | **{len(hosts)}个独立会话**：配速、取舍、伤害、未知保底，另对配速／取舍做最终合同发现复测；全部有完整回答、原参数及数值输出，UID查询0 |
| 实际工具重算 | 用最终实现重算全部真实宿主定量调用，数据逐项完全相同；tool-replay.json |
| 干净安装 | 最终0.1.2.dev1 wheel，新中文空格路径／新venv，**21条命令**通过；四类合同示例直接从安装包查询后执行，CLI/MCP及只读边界通过 |
| 原始文件 | 原PRD、两份规划哈希保持；37项共享基线检查通过；修复旧校验器将历史阶段证据表误算为责任表的问题，24个主要验收负责人仍各一次 |

软件0.1.2.dev1，API0.1.2，规则p3-1；已有知识0.2.0保持兼容。统一实验包含版本、来源、条件、投资口径、预算、规范化输入与内容指纹。CLI/MCP使用同一只读实现。阶段记录与各任务测试来源见 docs/development/task-status.json。

## 本阶段交付

D029 实验与比较合同；D030 普通直伤固定状态及单因素收益；D031 局部行动、变速、提前／延后、终结技窗口及能量／战技点合法性；D032 目标抽取状态DP、消耗分布、期望／分位数、未知保底范围；D033 三收入预算、顺序共享资源、多种取舍与不抽方案；D034本关口。

第一次真实配速／取舍计算数值正确，但Agent去开发目录读取schema。现增加 calculation_schema 和包内原创示例，最终两次新会话直接从工具取合同，仅shell读取已安装技能，未再读取开发目录。首轮轨迹没有删除，不能将其描述成全程无需查文件。开发虚拟环境旧元数据也已离线同步为0.1.2.dev1。

## 必须保留的边界

1. 伤害是固定状态普通直伤；未覆盖击破、持续、真实、欢愉及特殊桶，没有整场或游戏客户端高精度声明。极端抗性截断证据不足时拒绝，显示舍入未认证。
2. 时序没有敌人、状态持续、召唤物、额外回合和特殊资源；外部事件优先及同速顺序是显式模型假设。AV、事件、时间预算截断返回partial，资源不足的动作不会执行。
3. 官方硬规则与逐抽经验曲线分开；内置仅经典限定池情景，不是所有当前卡池精确概率。未知保底不猜状态或平均值，未来日期未知不编排期。
4. 抽取可达性与固定状态／定性收益分列，包含不抽方案；不把局部增伤写成账号收益。连续目标概率仅描述按顺序全部成功，条件期望不冒充无条件消耗。
5. 当前Codex仍没有原生业务确认回执连接器；沿用P2本地交互路径。本阶段未改变该权限边界。有限A风格合成会话不代替D054全面语义验收，另两宿主继续暂缓。
6. 宿主脚本有240秒防挂超时，完整新会话耗时约114～220秒（包含启动与模型输出）。120秒研究规则目前属于行为约束，不是全局强制墙钟承诺；后续仍由D039／D053完成统一长任务控制。
7. 本机沙箱 Path.resolve 对新测试目录的WinError5在修改前复现；正常宿主回归通过，因此离线回归经原生自动审查在沙箱外执行，产品路径保护没有放宽。官方帮助直连403时使用实际网页读取摘录，并明确哈希范围。

主要入口和样例见 README.md、docs/contracts/experiments.md；逐模块范围见 docs/validation/damage.md、timeline.md、gacha.md、planning.md。实际提示词和限制见 evals/scripts/quantitative-session.md，完整证据仅 .local/evidence/D029～D034。没有对外发布、没有选择总项目许可证、没有查询用户真实UID。

下一项是 **D035：封装正式模拟后端**，属于P4；本轮未开始。
'''
    (ROOT/"docs/gates/P3.md").write_text(report,encoding="utf-8")
    record("D034",status="DONE",summary=f"当前Codex范围P3通过：{len(cases)}核心+3后端预算测试、8公式对照、21条最终安装命令、6真实会话；数值与最终工具重算一致",
           artifacts=["docs/gates/P3.md","docs/gates/P3.json","docs/decisions/ADR-005-p3-quantitative.md","evals/scripts/quantitative-session.md"],
           evidence=[origin,".local/evidence/D034/simulator-budget.xml",".local/evidence/D034/semantic-review.json",".local/evidence/D034/tool-replay.json",".local/evidence/D034/fresh-install-summary.json"],
           commands=["python -X utf8 tools/p3/verify_codex.py --case <timeline/pulls/damage/unknown>","python -X utf8 tools/p3/verify_codex.py --case timeline --label timeline-self-contained",
                     "python -X utf8 tools/p3/verify_codex.py --case pulls --label pulls-self-contained","python -X utf8 tools/p3/fresh_install.py",
                     "python -X utf8 tools/p3/crosscheck_backend.py","python -X utf8 tools/p0/validate_p0.py --shared-only",
                     ".venv/Scripts/python.exe -X utf8 -m pytest tests --ignore=tests/p0 -m 'not live' -q --tb=short --basetemp=.local/tmp/pytest-p3-delivery --junitxml=.local/evidence/D034/regression-delivery.xml"],
           xml=origin,level="独立手算／穷举、离线合同、实际锁定后端表达式、真实Windows新环境wheel、真实Codex；不包含游戏内校准")
    print(json.dumps({"status":state["status"],"passed_core":len(cases),"passed_simulator":3,"actual_host_sessions":state["actual_host_sessions"],"next":"D035"},ensure_ascii=False))


if __name__ == "__main__":
    main()
