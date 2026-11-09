"""P0 evidence helpers. No application code, model calls, or account refresh."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
LOCAL = ROOT / ".local"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def command(args, *, task, name, cwd=ROOT, timeout=120, env=None):
    """Capture only an explicit command's stdout/stderr, never the environment."""
    started = time.perf_counter()
    child_env = (env if env is not None else os.environ).copy()
    child_env.update(PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    try:
        result = subprocess.run(
            [str(a) for a in args], cwd=cwd, env=child_env,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout,
        )
        record = {"args": [str(a) for a in args], "cwd": str(cwd),
                  "exit_code": result.returncode, "stdout": result.stdout,
                  "stderr": result.stderr, "timeout": False}
    except subprocess.TimeoutExpired as exc:
        def decode(value):
            return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value
        record = {"args": [str(a) for a in args], "cwd": str(cwd),
                  "exit_code": None, "stdout": decode(exc.stdout) or "",
                  "stderr": decode(exc.stderr) or "", "timeout": True}
    record.update(at=now(), seconds=round(time.perf_counter() - started, 4))
    evidence_path = LOCAL / "evidence" / task / (name + ".json")
    if evidence_path.exists():
        previous = evidence_path.with_name(name + ".previous-" + str(time.time_ns()) + ".json")
        previous.write_bytes(evidence_path.read_bytes())
    write_json(evidence_path, record)
    return record


def code_snapshot() -> str:
    h = hashlib.sha256()
    for directory in ("tools", "tests", "evals", "benchmarks", "manifests", "patches", "licenses"):
        for path in sorted((ROOT / directory).rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                h.update(path.relative_to(ROOT).as_posix().encode())
                h.update(path.read_bytes())
    return "sha256:" + h.hexdigest()


def render_ledger(tasks):
    lines = ["# 开发任务账本", "", "状态以实际验收为准；P0 以外任务尚未授权执行。",
             "详细命令、时间、计数和证据见同目录 task-status.json；本机原始日志在 .local/evidence/。", "",
             "| 任务 | 名称 | 直接依赖 | 状态 | 交付／证据／下一步 |",
             "|---|---|---|---|---|"]
    for task in tasks:
        # Keep every task ID exactly once in this table; dependencies use numbers.
        deps = ", ".join(d[1:] for d in task["dependencies"]) or "无"
        summary = task.get("summary", "待执行")
        lines.append(f'| {task["id"]} | {task["title"]} | {deps} | {task["status"]} | {summary} |')
    (ROOT / "docs/development/task-status.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def update_task(task_id, status, *, summary, artifacts=(), commands=(), counts=None,
                evidence=(), blockers=(), next_step="", level="离线文档／合同"):
    path = ROOT / "docs/development/task-status.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    task = next(t for t in data["tasks"] if t["id"] == task_id)
    if status in {"IN_PROGRESS", "DONE"}:
        incomplete = [d for d in task["dependencies"]
                      if next(t for t in data["tasks"] if t["id"] == d)["status"] != "DONE"]
        if incomplete:
            raise ValueError(f"{task_id}: incomplete dependencies: {incomplete}")
    task.update(status=status, summary=summary, artifacts=list(artifacts),
                commands=list(commands), test_counts=counts,
                evidence=list(evidence), blockers=list(blockers), next_step=next_step,
                validation_level=level, snapshot=code_snapshot(), updated_at=now())
    task["started_at"] = task.get("started_at") or now()
    if status == "DONE":
        task["completed_at"] = now()
    else:
        task["completed_at"] = None
    write_json(path, data)
    render_ledger(data["tasks"])
