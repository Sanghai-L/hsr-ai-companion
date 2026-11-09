"""P2 task records: evidence, status and reproducible source snapshots."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_json(path, value):
    path = ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def snapshot():
    digest = hashlib.sha256()
    for directory in ("src", "knowledge", "skills", "schemas", "migrations", "adapters", "tests", "evals", "tools/p2"):
        for path in sorted((ROOT / directory).rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                digest.update(path.relative_to(ROOT).as_posix().encode())
                digest.update(path.read_bytes())
    return "sha256:" + digest.hexdigest()


def render(ledger):
    lines = ["# 开发任务账本", "", "P0、P1 与 P2 均按实际证据登记；未通过的实际环境验收保留具体原因。",
             "详情见 task-status.json；本机日志位于 .local/evidence/。", "",
             "| 任务 | 名称 | 直接依赖 | 状态 | 交付／证据／下一步 |", "|---|---|---|---|---|"]
    for task in ledger["tasks"]:
        deps = ", ".join(d[1:] for d in task["dependencies"]) or "无"
        lines.append(f'| {task["id"]} | {task["title"]} | {deps} | {task["status"]} | {task.get("summary", "待执行")} |')
    (ROOT / "docs/development/task-status.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def record(task_id, *, status, summary, artifacts=(), evidence=(), commands=(), xml=None, blockers=(), level="离线合同"):
    ledger = json.loads((ROOT / "docs/development/task-status.json").read_bytes())
    task = next(t for t in ledger["tasks"] if t["id"] == task_id)
    if status == "DONE":
        assert all(next(t for t in ledger["tasks"] if t["id"] == d)["status"] == "DONE" for d in task["dependencies"])
        assert not blockers
    for path in [*artifacts, *evidence]:
        assert (ROOT / path).exists(), path
    counts = {"passed": 0, "failed": 0, "skipped": 0}
    if xml:
        cases = ET.parse(ROOT / xml).getroot().findall(".//testcase")
        counts["failed"] = sum(c.find("failure") is not None or c.find("error") is not None for c in cases)
        counts["skipped"] = sum(c.find("skipped") is not None for c in cases)
        counts["passed"] = len(cases) - counts["failed"] - counts["skipped"]
        if status == "DONE":
            assert counts["failed"] == 0 and counts["skipped"] == 0
    task.update(status=status, started_at=task.get("started_at") or now(), updated_at=now(), summary=summary,
                artifacts=list(artifacts), evidence=list(evidence), commands=list(commands), test_counts=counts,
                blockers=list(blockers), validation_level=level, snapshot=snapshot(),
                next_step=f"D{int(task_id[1:])+1:03}")
    if status == "DONE":
        task["completed_at"] = now()
    write_json("docs/development/task-status.json", ledger)
    render(ledger)
