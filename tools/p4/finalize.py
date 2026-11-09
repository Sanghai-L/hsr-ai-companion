"""Record only actual passing checks; unfinished dependencies stay unfinished."""
from copy import deepcopy
import hashlib
import json
import sys
import xml.etree.ElementTree as ET

from record import ROOT, now, record, snapshot, write_json


def subset(cases, name, predicate):
    selected = [case for case in cases if predicate(case)]
    assert selected
    assert all(case.find("failure") is None and case.find("error") is None and case.find("skipped") is None for case in selected)
    suite = ET.Element("testsuite", name=name, tests=str(len(selected)), failures="0", errors="0", skipped="0")
    suite.extend(deepcopy(selected))
    target = f".local/evidence/{name}/delivery-tests.xml"
    (ROOT / target).parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(suite).write(ROOT / target, encoding="utf-8", xml_declaration=True)
    write_json(f".local/evidence/{name}/test-origin.json", {"source_xml": ".local/evidence/D038/regression-delivery.xml",
               "selected_testcases": [c.get("classname") + "." + c.get("name") for c in selected],
               "extraction": "unchanged actual testcase nodes; not an additional execution"})
    return target


def main():
    from scope_audit import require_historical_finalizer_scope
    require_historical_finalizer_scope(ROOT)
    origin = ".local/evidence/D038/regression-delivery.xml"
    cases = ET.parse(ROOT / origin).getroot().findall(".//testcase")
    assert cases and all(c.find("failure") is None and c.find("error") is None and c.find("skipped") is None for c in cases)
    command = ".venv/Scripts/python.exe -X utf8 -m pytest tests --ignore=tests/p0 -m 'not live' -q --tb=short --basetemp=.local/tmp/pytest-p4-delivery-final --junitxml=.local/evidence/D038/regression-delivery.xml"
    predicates = {
        "D035": lambda c: c.get("classname") == "tests.simulation.test_backend_adapter",
        "D036": lambda c: c.get("classname") == "tests.simulation.test_coverage_gate" or (c.get("classname") == "tests.simulation.test_transport" and "account_build_import" not in c.get("name")),
        "D037": lambda c: c.get("classname") == "tests.simulation.test_build_import" or (c.get("classname") == "tests.simulation.test_transport" and "account_build_import" in c.get("name")),
        "D038": lambda c: c.get("classname") in {"tests.modes.test_moc", "tests.modes.test_scenario_candidate"},
    }
    summaries = {
        "D035": "正式隔离后端：与P0两队全部业务事件/快照/伤害样本等价，代码/数据/补丁/桥接指纹及结构化错误通过；未授予游戏精度资格",
        "D036": "50项机制登记与输入交集检查；未知装备触发器、敌人阶段、精度拦截及告警跨CLI/MCP保留；未支持机制不自动归零",
        "D037": "只读快照/手工/假设构筑，实例占用、形态、面板防二次叠加、单位/速度精度及明确绑定限制通过；账号字节保持、UID查询0",
        "D038": "历史场景数值/抗性绑定与源解析通过；按用户选择整理4.6源1036/11上下半，实际角色实体已私有登记；完整AI/阶段/关卡效果及缺模板尚未解决，人工核对按用户要求稍后再测",
    }
    artifacts = {
        "D035": ["src/companion/sim_backends/", "manifests/simulator.lock.json", "tests/simulation/test_backend_adapter.py", "docs/contracts/simulation.md"],
        "D036": ["manifests/coverage.json", "src/companion/simulation/preflight.py", "tests/simulation/test_coverage_gate.py", "tests/fixtures/requests/simulation.json"],
        "D037": ["src/companion/simulation/builds.py", "schemas/simulation-build.schema.json", "manifests/build-catalog.json", "tests/simulation/test_build_import.py", "tests/fixtures/builds/"],
        "D038": ["src/companion/modes/memory_of_chaos.py", "src/companion/modes/scenario_candidate.py", "benchmarks/modes/moc/", "docs/development/P4-remaining.md", "docs/gates/P4-alpha.md"],
    }
    for task in ("D035", "D036", "D037", "D038"):
        target = subset(cases, task, predicates[task])
        evidence = [origin, target, f".local/evidence/{task}/test-origin.json"]
        if task == "D035":
            evidence += [".local/evidence/D035/baseline.xml", ".local/evidence/D035/baseline-native.xml"]
        if task == "D038":
            evidence += [".local/evidence/D038/scene-audit.json", ".local/evidence/D038/diagnostic-summary.json",
                         ".local/evidence/D038/fresh-install-summary.json", ".local/evidence/D038/core-budget.xml",
                         ".local/evidence/D038/source-recheck.json", ".local/evidence/D038/current-1036-11/preparation-summary.json"]
        blockers = (["完整敌人AI/阶段/关卡效果缺少可执行实现与逐事件依据", "当前所选队伍有缺失模板/未知构筑字段",
                     "用户已明确稍后进行人工核对，未取得外部观察，不得认证完整场景"] if task == "D038" else [])
        record(task, status="BLOCKED" if task == "D038" else "DONE", summary=summaries[task], artifacts=artifacts[task],
               evidence=evidence, commands=[command], xml=target, blockers=blockers,
               level="真实锁定模拟核心/离线合同；独立合成手算与公开源核对。D038仅部分场景/数据适配，不是完整游戏验收")

    # Retain P0 evidence; add current implementation findings without rewriting
    # the old snapshot, original task contract or candidate replay results.
    gaps = json.loads((ROOT / "manifests/simulator-gaps.json").read_bytes())
    gaps["p4_followup"] = {"at": now(), "status": "D038_BLOCKED", "precision_certified": False,
                           "fixed_in_adapter": ["SIM-004:stage-specific stat-group binding", "SIM-005:base elemental resistance import"],
                           "still_missing": ["SIM-003:full enemy AI/phase", "SIM-005:special mitigation/phase", "SIM-006:character caveats", "SIM-007:external calibration"],
                           "current_candidate": {"period_source_id": "1036", "floor": 11, "sides": ["upper", "lower"],
                                                 "live_source_marker": "4.6", "manual_observation": "DEFERRED_BY_USER"},
                           "evidence": ".local/evidence/D038/"}
    write_json("manifests/simulator-gaps.json", gaps)
    catalog = json.loads((ROOT / "benchmarks/catalog.json").read_bytes())
    catalog["p4_development"] = {"status": "D038_BLOCKED", "source_aligned_candidate": ".local/benchmarks/user-selected-moc-1036-11/scenario-candidate.json",
        "selected_rosters": ".local/benchmarks/user-selected-moc-1036-11/selected-rosters.json", "complete_supported": False,
        "historical_case_preserved": True, "manual_observation": "DEFERRED_BY_USER"}
    write_json("benchmarks/catalog.json", catalog)
    ledger = json.loads((ROOT / "docs/development/task-status.json").read_bytes())
    final_snapshot = snapshot()
    for task in ledger["tasks"]:
        if task["id"] in {"D035", "D036", "D037", "D038"}:
            task["snapshot"] = final_snapshot
    write_json("docs/development/task-status.json", ledger)
    sys.path.insert(0, str(ROOT / "tools/p0"))
    from validate_p0 import validate
    baseline = validate(shared_only=True)
    write_json(".local/evidence/D038/shared-baseline.json", baseline)
    install = json.loads((ROOT / ".local/evidence/D038/fresh-install-summary.json").read_bytes())
    assert install["status"] == "PASS" and install["uid_queries"] == 0
    gate = {"at": now(), "status": "NOT_PASSED_D038_BLOCKED", "tasks_done": ["D035", "D036", "D037"], "blocked": ["D038"],
            "not_started": ["D039", "D040", "D041", "D042"], "host_scope": ["codex"], "game_accuracy_certified": False,
            "offline_regression": {"passed": len(cases), "failed": 0, "skipped": 0, "live_deselected": 1, "source": origin},
            "isolated_core_budget": {"passed": 3, "source": ".local/evidence/D038/core-budget.xml"},
            "fresh_install_commands": install["commands"], "shared_baseline_checks": baseline["passed"], "uid_queries": 0,
            "current_candidate": {"name": "物竞天择", "period_source_id": "1036", "floor": 11, "sides": ["upper", "lower"],
                                  "source_aligned": True, "region": None, "manual_observation_status": "DEFERRED_BY_USER"}}
    write_json("docs/gates/P4-alpha.json", gate)
    print(json.dumps({"status": gate["status"], "passed": len(cases), "shared_baseline": baseline["passed"], "done": gate["tasks_done"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
