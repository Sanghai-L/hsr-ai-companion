"""Record D029-D033 using subsets of the actual delivery regression XML."""
from copy import deepcopy
import xml.etree.ElementTree as ET

from record import ROOT, record, write_json

CASES = [
    ("D029", "tests.experiments.test_contracts", "实验规范化、关键条件指纹、具体缺项、真实账号快照及不同口径比较门禁通过",
     ["schemas/experiment.schema.json", "schemas/comparison.schema.json", "src/companion/experiments/", "docs/contracts/experiments.md"], []),
    ("D030", "tests.calculators.test_damage", "普通直伤逐乘区手算、单因素收益及边界通过；锁定后端8个真实表达式对照通过，非游戏校准",
     ["src/companion/calculators/damage.py", "benchmarks/formulas/", "docs/validation/damage.md", "tests/fixtures/requests/damage.json"],
     [".local/evidence/D030/backend-crosscheck.json", ".local/evidence/D030/backend-expression-process.json", ".local/evidence/D030/source-capture.json"]),
    ("D031", "tests.calculators.test_timeline_resources", "变速保留距离、提前／延后、能量／战技点原子校验、终结技窗口、精度范围及三类预算终止通过",
     ["src/companion/calculators/timeline.py", "src/companion/calculators/resources.py", "docs/validation/timeline.md", "tests/fixtures/requests/timeline.json"], []),
    ("D032", "tests.calculators.test_gacha", "状态DP与独立概率树穷举一致；概率质量、零预算／硬保底／保证／多目标／跨池隔离／未知范围和预算通过",
     ["src/companion/calculators/gacha.py", "schemas/banner-rules.schema.json", "docs/validation/gacha.md", "tests/fixtures/requests/gacha.json"], []),
    ("D033", "tests.planning.test_budget_pulls", "三收入情景、来源去重、共享预算连续目标、池独立、未知日期与保底、不抽及固定状态收益分列通过",
     ["src/companion/planning/", "tests/planning/", "evals/cases/pull-plans.json", "docs/validation/planning.md"], []),
]


def main():
    origin = ".local/evidence/D034/regression-delivery.xml"
    cases = ET.parse(ROOT/origin).getroot().findall(".//testcase")
    for task, classname, summary, artifacts, evidence in CASES:
        selected = [c for c in cases if c.get("classname") == classname]
        assert selected and all(c.find("failure") is None and c.find("error") is None and c.find("skipped") is None for c in selected)
        target = f".local/evidence/{task}/tests.xml"
        suite = ET.Element("testsuite",name=f"{task} subset of actual delivery regression",tests=str(len(selected)),failures="0",errors="0",skipped="0")
        suite.extend(deepcopy(selected))
        (ROOT/target).parent.mkdir(parents=True,exist_ok=True)
        ET.ElementTree(suite).write(ROOT/target,encoding="utf-8",xml_declaration=True)
        write_json(f".local/evidence/{task}/test-origin.json",{"source_xml":origin,"selected_classname":classname,"passed":len(selected),
                   "extraction":"unchanged actual testcase nodes; not an additional claimed execution"})
        record(task,status="DONE",summary=summary,artifacts=artifacts,evidence=[origin,target,*evidence],xml=target,
               commands=[".venv/Scripts/python.exe -X utf8 -m pytest tests --ignore=tests/p0 -m 'not live' -q --tb=short --basetemp=.local/tmp/pytest-p3-delivery --junitxml=.local/evidence/D034/regression-delivery.xml"],
               level="离线合同／独立手算与穷举；D030另有真实锁定后端公式表达式及公开来源正文核对")
    record("D034",status="IN_PROGRESS",summary="离线回归与最终安装通过；正在审阅真实 Codex 合同发现复测和数值／回答一致性",
           artifacts=["evals/scripts/quantitative-session.md", "tools/p3/verify_codex.py"],evidence=[origin])
    print("D029-D033 DONE; D034 awaiting final host review")


if __name__ == "__main__":
    main()
