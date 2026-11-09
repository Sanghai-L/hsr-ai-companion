"""Small stage journal: preserve earlier evidence and require completed dependencies."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def write(path, value):
    path = ROOT/path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")


def record(task_id, *, status, artifacts, commands, evidence, summary, counts=None, blockers=None):
    path = ROOT/"docs/development/task-status.json"
    ledger = json.loads(path.read_bytes())
    task = next(t for t in ledger["tasks"] if t["id"] == task_id)
    if status == "DONE":
        assert all(next(t for t in ledger["tasks"] if t["id"] == d)["status"] == "DONE" for d in task["dependencies"])
        assert all((ROOT/a).exists() for a in artifacts+evidence)
        assert counts and counts["failed"] == counts["skipped"] == 0
    at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rows = [(p.relative_to(ROOT).as_posix(), hashlib.sha256(p.read_bytes()).hexdigest())
            for parent in ("src/companion", "schemas", "manifests", "migrations", "adapters", "skills")
            for p in sorted((ROOT/parent).rglob("*")) if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"]
    task.update(status=status, started_at=task.get("started_at") or at, completed_at=at if status == "DONE" else None,
                updated_at=at, snapshot="sha256:"+hashlib.sha256(json.dumps(rows, ensure_ascii=False).encode()).hexdigest(),
                artifacts=artifacts, commands=commands, evidence=evidence, summary=summary,
                test_counts=counts, blockers=blockers or [], next_step=f"D{int(task_id[1:])+1:03}" if status == "DONE" else summary)
    write("docs/development/task-status.json", ledger)
    completed = all(item["status"] == "DONE" for item in ledger["tasks"])
    header = "# 开发任务账本\n\n" + ("D001～D058 已在当前 Windows／Codex 授权范围完成。" if completed else "P6 按编号推进。") + "证据及历史记录以 task-status.json 为准；另两宿主继续暂缓。\n\n"
    table = "| 任务 | 名称 | 直接依赖 | 状态 | 交付／证据／下一步 |\n|---|---|---|---|---|\n"
    for t in ledger["tasks"]:
        table += f"| {t['id']} | {t['title']} | {'、'.join(t['dependencies']) or '无'} | {t['status']} | {t.get('summary', t.get('next_step', '待执行'))} |\n"
    (ROOT/"docs/development/task-status.md").write_text(header+table, encoding="utf-8")
