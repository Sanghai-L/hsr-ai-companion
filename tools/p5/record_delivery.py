"""Record evidence without promoting protocol tests into fresh model acceptance."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = {
    "D038": ["src/companion/simulation/rotation.py", "schemas/representative-comparison.schema.json", "benchmarks/modes/moc/representative-v1.json"],
    "D039": ["src/companion/jobs/__init__.py", "tests/jobs/test_control.py"],
    "D040": ["src/companion/simulation/compare.py", "tests/simulation/test_fairness_statistics.py"],
    "D041": ["src/companion/experiments/replay.py", "src/companion/simulation/explain.py", "tools/run_demo_comparison.py", "tests/experiments/test_representative_replay.py"],
    "D042": ["docs/validation/alpha-comparison.md", "docs/gates/P4-alpha.md"],
    "D043": ["benchmarks/archetypes/catalog.json"],
    "D044": ["src/companion/modes/pure_fiction.py", "benchmarks/modes/pf/representative-v1.json", "tests/modes/test_pf.py"],
    "D045": ["src/companion/modes/apocalyptic_shadow.py", "benchmarks/modes/as/representative-v1.json", "tests/modes/test_as.py"],
    "D046": ["src/companion/modes/anomaly_arbitration.py", "docs/modes/anomaly-arbitration-spec.md", "tests/modes/test_aa.py"],
    "D047": ["src/companion/planning/multi_team.py", "tests/planning/test_multi_team.py", "evals/cases/multi-team.json"],
    "D048": ["src/companion/sources/current_stages.py", "src/companion/planning/sensitivity.py", "tests/sources/test_current_stages.py", "tests/planning/test_sensitivity.py"],
    "D049": ["docs/coverage.md", "docs/gates/P5-beta.md", "tools/p5/run_checks.py", "tools/p5/fresh_install.py"],
}
SUMMARIES = [
    "代表性固定窗口：有来源两队技能、资源收支、关键缺项拒绝与独立手算通过；原严格模型保留",
    "同步有界预算与协作取消；部分结果不排名，无后台工作进程，不宣称断点续算",
    "同条件少量候选比较、并列、投资口径、A/B互换与缺项测试通过",
    "私有实验事务保存、方法与实现指纹、账号隔离、真实SQLite重开与从头重算通过",
    "简化计算及隔离安装通过；真实Codex新会话行为关口待授权",
    "已准备单体／对群跨血线案例与来源；待D042通过后按顺序登记正式验收",
    "已准备虚构目标密度、补怪假设与显式跨血线比较；待D042前置关口",
    "已准备末日击破前后输出、削韧容量和资源窗口；待D042前置关口",
    "已准备异相通用规则、骑士比较与定量／定性界限；待D042前置关口",
    "已准备角色／形态／装备实例冲突、多队穷举及王棋复用；待前置顺序验收",
    "已准备当前来源冻结／降级及1～2参数反转检查；待前置顺序验收",
    "四模式代码及本地回归已具备；正式Beta待D042及后续顺序关口完成",
]


def read(path):
    return json.loads(Path(path).read_bytes())


def write(path, value):
    path = ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def relative(path):
    path = Path(path).resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError("evidence must stay inside workspace")
    return path.relative_to(ROOT).as_posix()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--regression", type=Path, required=True)
    parser.add_argument("--install", type=Path, required=True)
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--host-audit", type=Path)
    args = parser.parse_args()
    if not args.host_audit:
        existing = read(ROOT / "docs/development/task-status.json")
        alpha = next(task for task in existing["tasks"] if task["id"] == "D042")
        if alpha.get("host_authorization", {}).get("authorized") or alpha["status"] == "DONE":
            raise RuntimeError("真实宿主验收已授权或完成；不可回写待授权状态。请传入实际--host-audit证据，未修改记录。")
    regression, install, sources = relative(args.regression), relative(args.install), relative(args.sources)
    records = ET.parse(ROOT / regression).getroot().findall(".//testcase")
    counts = {"passed": sum(not any(case.find(t) is not None for t in ["failure", "error", "skipped"]) for case in records),
              "failed": sum(any(case.find(t) is not None for t in ["failure", "error"]) for case in records),
              "skipped": sum(case.find("skipped") is not None for case in records)}
    assert counts["passed"] and counts["failed"] == counts["skipped"] == 0
    command_record = read((ROOT / regression).with_suffix(".json"))
    assert command_record["exit_code"] == 0
    fresh = read(ROOT / install)
    assert fresh["status"] == "PASS" and fresh["model_calls"] == fresh["uid_queries"] == 0
    with zipfile.ZipFile(fresh["wheel"]) as archive:
        for file in (ROOT / "src/companion").rglob("*.py"):
            assert archive.read("companion/" + file.relative_to(ROOT / "src/companion").as_posix()) == file.read_bytes(), str(file)
    assert read(ROOT / sources)["results"]["memory_of_chaos"]["data"]["current_confirmed"] is False
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    host = None
    host_path = None
    if args.host_audit:
        host_path = relative(args.host_audit)
        host = read(ROOT / host_path)
        assert host["status"] == "PASS" and host["model_sessions"] == 5
        assert all(host["checks"].values()) and host["uid_queries"] == host["snapshots"] == 0
        assert len(set(host["session_ids"])) == 5
        for trace in host["trace_files"]:
            assert Path(trace).is_file()
    for path in ["docs/gates/P4-alpha.md", "docs/development/P4-remaining.md"]:
        file = ROOT / path
        archive = file.parent / "archive" / (file.stem + "-before-p5.md")
        if not archive.exists():
            archive.parent.mkdir(parents=True, exist_ok=True)
            archive.write_bytes(file.read_bytes())
    evidence = [regression, install, sources, ".local/evidence/D041/p5-demo-v1/result.json"]
    if host:
        evidence.append(host_path)
    gate = {"at": now, "delivery_schema": 1, "status": "ENGINEERING_PASS_HOST_PENDING",
            "formal_gate_passed": False, "host_scope": ["codex"], "actual_new_model_session_tested": False,
            "offline_regression": counts | {"live_deselected": 1, "source": regression},
            "fresh_install": {"commands": fresh["commands"], "evidence": install, "layer": fresh["layer"]},
            "current_stage_source_evidence": sources, "uid_queries": 0, "additional_model_calls": 0,
            "game_accuracy_certified": False, "pending": ["D042真实Codex新会话问答、保存与恢复；额外模型额度授权已询问，尚无答复", "D049真实宿主四模式选择验收及正式顺序关口"],
            "scope": "实现和离线／真实进程证据已具备；不把协议重启或源码存在当作新模型会话验收"}
    if host:
        gate.update(status="PASS_SIMPLIFIED_SCOPE", formal_gate_passed=True, actual_new_model_session_tested=True,
                    actual_host_evidence=host_path, additional_model_sessions=host["model_sessions"],
                    additional_model_calls=None, pending=[],
                    host_checks=host["checks"], model_usage=host["usage"],
                    scope="当前Codex范围的真实新会话、四模式分析、保存恢复和指定假设比较通过；完整游戏精度未宣称支持")
    old_gate = read(ROOT / "docs/gates/P4-alpha.json")
    gate["previous_gate"] = old_gate.get("previous_gate", old_gate) if old_gate.get("delivery_schema") else old_gate
    write("docs/gates/P4-alpha.json", gate)
    write("docs/gates/P5-beta.json", {k: v for k, v in gate.items() if k != "previous_gate"})
    for name, title in [("P4-alpha", "P4简化比较与Alpha"), ("P5-beta", "P5四模式比较与Beta")]:
        content = f"""# {title}关口

日期：{now[:10]}。状态：**ENGINEERING_PASS_HOST_PENDING**；正式关口尚未通过。

本轮已补齐P4计算前置，P5四模式分析、多队分配、来源降级、敏感性复算及保存重算均已实现。离线全量回归 **{counts['passed']}通过、0失败、0跳过**；1项UID联网测试明确未选择。实际wheel、新Windows虚拟环境、中文空格路径及独立CLI／MCP进程共 **{fresh['commands']}条命令通过**，其中包括实验保存、重算和新进程找回个人研究。

这些是实际代码、SQLite、进程和安装证据。**真实Codex新模型会话尚未启动**，额外模型额度授权已询问、尚无答复；不将协议测试或当前开发会话冒充该验收。D042保持进行中；D043～D049已有本地实现准备，正式验收按D042通过后的依赖顺序登记，当前不标DONE。

当前数值覆盖只包括指定E0、无大行迹的假设动作窗口。完整敌人AI、游戏精确分数、通关概率和全角色队伍覆盖未宣称支持；详见[实际覆盖](../coverage.md)及[算术验证](../validation/alpha-comparison.md)。来源实读已冻结，但排期／区服不足，不能确认当前环境。没有查询UID、启动游戏、修改真实玩家资料或对外发布。

证据：`{regression}`；`{install}`；`{sources}`；`.local/evidence/D041/p5-demo-v1/`。早先失败日志原样保留；原P4说明保存在`archive/P4-alpha-before-p5.md`，原JSON通过previous_gate保留。
"""
        (ROOT / f"docs/gates/{name}.md").write_text(content, encoding="utf-8")
        if host:
            complete = f"""# {title}关口

日期：{now[:10]}。状态：**PASS_SIMPLIFIED_SCOPE**；当前Codex范围的简化比较关口通过。

离线全量回归 **{counts['passed']}通过、0失败、0跳过**，1项UID联网测试明确未选择。实际wheel、新Windows虚拟环境、中文空格路径及独立CLI／MCP进程共 **{fresh['commands']}条命令通过**。安装验证的源码与当前源码逐文件一致。

用户在2026-11-08明确回复“允许”后，执行了 **{host['model_sessions']}个真实全新Codex模型会话**，使用此前验证的安装包及项目级MCP、合成账号。混沌比较后由模型真实保存实验及带引用的私人研究；另一个全新会话找回原研究、读取实验引用并从保存输入重算一致。虚构、末日和异相分别选中实际分析模板；虚构目标数复算给出推荐反转，未验证占位角色返回缺项且不排名；异相三骑士方案无角色／装备实例重复，王棋复用规则保留。

真实模型最终回答经人工审阅，数值与实际工具结果一致，明确保留假设、未量化机制及非实战得分／必胜的界限。参数误填后被工具拒绝并自行纠正的调用保留在轨迹及audit.json中，没有隐藏失败或把错误输出计为通过。

D038～D049按直接依赖顺序完成登记。当前仍只量化清单内指定E0、无大行迹的假设动作窗口；完整敌人AI、全角色机制、当前环境排名、精确游戏分数与通关概率未宣称支持。公开来源实读已冻结，但排期／区服不足，不能确认当前期数。没有查询UID、启动游戏、修改真实玩家资料、改全局宿主配置或对外发布；另两宿主继续暂缓。

证据：`{regression}`；`{install}`；`{sources}`；`{host_path}`；`.local/evidence/D041/p5-demo-v1/`。详情见[覆盖说明](../coverage.md)和[算术验证](../validation/alpha-comparison.md)。原P4 JSON通过previous_gate保留，旧说明存于archive目录。下一阶段P6尚未开始。
"""
            (ROOT / f"docs/gates/{name}.md").write_text(complete, encoding="utf-8")
    ledger = read(ROOT / "docs/development/task-status.json")
    files = {}
    for directory in ["src", "schemas", "tests", "benchmarks", "manifests", "adapters", "skills", "tools/p5"]:
        for path in (ROOT / directory).rglob("*"):
            if path.is_file() and "__pycache__" not in path.parts:
                files[path.relative_to(ROOT).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    code_snapshot = "sha256:" + hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
    for index, task_id in enumerate(ARTIFACTS):
        task = next(t for t in ledger["tasks"] if t["id"] == task_id)
        for path in ARTIFACTS[task_id]:
            assert (ROOT / path).exists(), path
        if not task.get("p5_preparation"):
            task.setdefault("implementation_history", []).append(deepcopy({k: v for k, v in task.items() if k != "implementation_history"}))
        if int(task_id[1:]) < 42:
            assert all(next(t for t in ledger["tasks"] if t["id"] == dep)["status"] == "DONE" for dep in task["dependencies"])
            task.update(status="DONE", started_at=task.get("started_at") or now, completed_at=task.get("completed_at") or now,
                        artifacts=ARTIFACTS[task_id], evidence=evidence, test_counts=counts, blockers=[],
                        commands=[command_record["command"], [str(ROOT / ".venv/Scripts/python.exe"), "tools/p5/fresh_install.py"]],
                        exit_codes=[0, 0], validation_level="离线合同／独立手算／真实SQLite和Windows进程／实际wheel；不含新模型会话",
                        snapshot=code_snapshot, next_step=f"D{int(task_id[1:])+1:03}")
        elif task_id == "D042":
            task.update(status="IN_PROGRESS", started_at=task.get("started_at") or now, completed_at=None,
                        artifacts=ARTIFACTS[task_id], evidence=evidence, test_counts=counts,
                        blockers=["真实Codex新会话验收需要额外模型额度授权；已询问，尚无答复"], next_step="完成已准备的真实宿主验收")
        else:
            # Prepared code does not satisfy a missing direct predecessor gate.
            task.update(status="NOT_STARTED", completed_at=None,
                        blockers=["D042真实宿主前置关口尚未通过；本地代码与验证已经准备"])
        if host and int(task_id[1:]) >= 42:
            assert all(next(t for t in ledger["tasks"] if t["id"] == dep)["status"] == "DONE" for dep in task["dependencies"])
            task.update(status="DONE", started_at=task.get("started_at") or task.get("p5_preparation", {}).get("prepared_at") or now,
                        completed_at=task.get("completed_at") or now, artifacts=ARTIFACTS[task_id], evidence=evidence, test_counts=counts,
                        commands=[command_record["command"], [str(ROOT/".venv/Scripts/python.exe"), "tools/p5/audit_host.py", "--plan", host["plan"]]],
                        exit_codes=[0, 0], blockers=[], snapshot=code_snapshot,
                        validation_level="离线／独立手算／实际wheel／真实Codex新会话与MCP及SQLite",
                        host_evidence=host_path, next_step=f"D{int(task_id[1:])+1:03}")
        task.update(summary=SUMMARIES[index], updated_at=now,
                    p5_preparation={"implementation_available": True, "artifacts": ARTIFACTS[task_id], "evidence": evidence,
                                    "offline_test_counts": counts, "prepared_at": now, "snapshot": code_snapshot})
        if host and int(task_id[1:]) >= 42:
            summaries = {"D042": "真实Codex比较→实验与研究保存→新会话找回原实验重算一致；简化Alpha通过",
                         "D043": "有来源单体／对群跨血线案例可比较，目标数改变推荐；未知角色不纳入排名",
                         "D044": "虚构密度／补怪／跨血线条件比较及真实宿主参数反转验收通过，不换算得分",
                         "D045": "末日击破前后直伤／削韧容量／资源窗口及真实宿主输出通过，不推断精确分数",
                         "D046": "异相规则、骑士配置比较和定量／定性界限经真实宿主验证，当前期数缺口明示",
                         "D047": "三骑士候选分配无角色／形态／装备实例冲突，王棋可复用；穷举与真实宿主通过",
                         "D048": "正式服来源参数冻结、区服排期不足降级；关键参数反转由实际工具与宿主确认",
                         "D049": "300项离线回归、25条隔离安装命令及5个真实新会话通过；当前Codex简化Beta通过"}
            task["summary"] = summaries[task_id]
    write("docs/development/task-status.json", ledger)
    lines = ["# 开发任务账本", "", "2026-11-08：D038～D041简化实现与本地验收完成；D042真实宿主关口待授权。", "P5代码和离线验证已准备，正式验收仍按D042后的依赖顺序登记，不以准备状态替代DONE。", "详见P4／P5关口及task-status.json；历史证据保留。", "", "| 任务 | 名称 | 直接依赖 | 状态 | 交付／证据／下一步 |", "|---|---|---|---|---|"]
    if host:
        lines[2:4] = ["2026-11-08：用户授权后的真实Codex验收通过，D038～D049按直接依赖顺序完成；P5简化范围Beta通过。", "300项离线回归、25条实际wheel安装命令及5个真实新会话；完整游戏精度未宣称支持，P6尚未开始。"]
    for task in ledger["tasks"]:
        lines.append(f"| {task['id']} | {task['title']} | {'、'.join(task['dependencies']) or '无'} | {task['status']} | {task.get('summary', '待执行')} |")
    (ROOT / "docs/development/task-status.md").write_text("\n".join(lines)+"\n", encoding="utf-8")
    (ROOT / "docs/development/P4-remaining.md").write_text("# P4剩余工作\n\nD038～D041的简化计算、预算、比较、解释及输入重算已经实现并通过本地验收。D042余下真实Codex新会话问答／保存／恢复验收；已请求额外模型额度授权，尚无答复。\n\nP5四模式、多队、来源降级和敏感性已准备，正式阶段验收继续按D042→D049执行。详见[当前关口](../gates/P5-beta.md)。不要求用户补敌人动作表或人工整场观察。原调查和用户选择原样保存在`archive/P4-remaining-before-p5.md`及.local历史目录。\n", encoding="utf-8")
    if host:
        (ROOT / "docs/development/P4-remaining.md").write_text("# P4后续状态\n\nD038～D042已按简化范围完成；用户授权后的真实Codex比较、保存和新会话找回重算通过。P5的D043～D049随后按依赖完成登记，见[P5关口](../gates/P5-beta.md)。当前下一项D050，P6尚未开始。完整敌人AI和人工整场观察仍是可选增强，不恢复为必做前提。原调查保存在archive和.local历史目录。\n", encoding="utf-8")
    write(".local/evidence/D049/delivery-index.json", {"at": now, "status": gate["status"], "evidence": evidence,
          "files": files, "snapshot": code_snapshot, "formal_gate_passed": bool(host)})
    print(json.dumps({"status": gate["status"], "regression": counts, "fresh_install_commands": fresh["commands"], "next": "D050" if host else "D042真实宿主验收待授权"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
