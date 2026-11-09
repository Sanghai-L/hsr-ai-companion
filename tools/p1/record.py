"""Record real command results without altering P0 completion evidence."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def snapshot():
    digest = hashlib.sha256()
    for directory in ("src", "schemas", "migrations", "adapters", "tests", "tools/p1"):
        for path in sorted((ROOT / directory).rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                digest.update(path.relative_to(ROOT).as_posix().encode())
                digest.update(path.read_bytes())
    for name in ("pyproject.toml", "requirements.in", "requirements.lock"):
        digest.update((ROOT / name).read_bytes())
    return "sha256:" + digest.hexdigest()


def record(task_id, *, artifacts, commands, evidence, summary, xml=None, level="离线合同／真实 Windows 本地进程"):
    path = ROOT / "docs/development/task-status.json"
    ledger = json.loads(path.read_text(encoding="utf-8"))
    task = next(t for t in ledger["tasks"] if t["id"] == task_id)
    assert all(next(t for t in ledger["tasks"] if t["id"] == dep)["status"] == "DONE"
               for dep in task["dependencies"]), "Incomplete dependencies"
    counts = {"passed": 0, "failed": 0, "skipped": 0}
    if xml:
        cases = ET.parse(ROOT / xml).getroot().findall(".//testcase")
        counts["failed"] = sum(c.find("failure") is not None or c.find("error") is not None for c in cases)
        counts["skipped"] = sum(c.find("skipped") is not None for c in cases)
        counts["passed"] = len(cases) - counts["failed"] - counts["skipped"]
        assert counts["failed"] == 0 and counts["skipped"] == 0 and counts["passed"] > 0
    for artifact in artifacts:
        assert (ROOT / artifact).exists(), artifact
    for item in evidence:
        assert (ROOT / item).exists(), item
    task.update(status="DONE", started_at=task.get("started_at") or now(), completed_at=now(),
                updated_at=now(), snapshot=snapshot(), artifacts=artifacts, commands=commands,
                evidence=evidence, test_counts=counts, blockers=[], validation_level=level,
                next_step=f"D{int(task_id[1:])+1:03}", summary=summary)
    path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    render(ledger)


def render(ledger):
    lines = ["# 开发任务账本", "", "P0 及本轮 P1 按实际证据登记；P2 以后尚未开始。",
             "详情见 task-status.json；本机日志位于 .local/evidence/。", "",
             "| 任务 | 名称 | 直接依赖 | 状态 | 交付／证据／下一步 |", "|---|---|---|---|---|"]
    for task in ledger["tasks"]:
        deps = ", ".join(d[1:] for d in task["dependencies"]) or "无"
        lines.append(f'| {task["id"]} | {task["title"]} | {deps} | {task["status"]} | {task.get("summary", "待执行")} |')
    (ROOT / "docs/development/task-status.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("input", help="JSON completion record")
    args = parser.parse_args()
    record(**json.loads(Path(args.input).read_text(encoding="utf-8")))

