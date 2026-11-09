"""P4 evidence ledger, retaining earlier stage records and raw failures."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_json(relative, value):
    path = ROOT / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def snapshot():
    digest = hashlib.sha256()
    for directory in ("src", "schemas", "skills", "adapters", "tests", "benchmarks", "manifests", "tools/p4"):
        for path in sorted((ROOT / directory).rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                digest.update(path.relative_to(ROOT).as_posix().encode())
                digest.update(path.read_bytes())
    return "sha256:" + digest.hexdigest()


def record(task_id, *, status, summary, artifacts=(), evidence=(), commands=(), xml=None, blockers=(), level="离线合同"):
    ledger = json.loads((ROOT / "docs/development/task-status.json").read_bytes())
    task = next(t for t in ledger["tasks"] if t["id"] == task_id)
    if status in {"IN_PROGRESS", "DONE"}:
        assert all(next(t for t in ledger["tasks"] if t["id"] == dep)["status"] == "DONE" for dep in task["dependencies"])
    if status == "DONE":
        assert not blockers
    for path in (*artifacts, *evidence):
        assert (ROOT / path).exists(), path
    counts = {"passed": 0, "failed": 0, "skipped": 0}
    if xml:
        cases = ET.parse(ROOT / xml).getroot().findall(".//testcase")
        counts["failed"] = sum(c.find("failure") is not None or c.find("error") is not None for c in cases)
        counts["skipped"] = sum(c.find("skipped") is not None for c in cases)
        counts["passed"] = len(cases) - counts["failed"] - counts["skipped"]
        if status == "DONE":
            assert counts["passed"] and not counts["failed"] and not counts["skipped"]
    task.update(status=status, started_at=task.get("started_at") or now(), updated_at=now(), summary=summary,
                artifacts=list(artifacts), evidence=list(evidence), commands=list(commands), test_counts=counts,
                blockers=list(blockers), validation_level=level, snapshot=snapshot(), next_step=f"D{int(task_id[1:])+1:03}")
    if status == "DONE":
        task["completed_at"] = now()
    write_json("docs/development/task-status.json", ledger)
    lines = ["# 开发任务账本", "", "P0～P4 按实际证据登记；宿主范围沿用用户决定，未通过项保留具体原因。",
             "详情见 task-status.json；本机日志位于 .local/evidence/。", "",
             "| 任务 | 名称 | 直接依赖 | 状态 | 交付／证据／下一步 |", "|---|---|---|---|---|"]
    for item in ledger["tasks"]:
        deps = ", ".join(d[1:] for d in item["dependencies"]) or "无"
        lines.append(f'| {item["id"]} | {item["title"]} | {deps} | {item["status"]} | {item.get("summary", "待执行")} |')
    (ROOT / "docs/development/task-status.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
