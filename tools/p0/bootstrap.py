"""D001: preserve requirements and initialize the 58-task ledger."""
from pathlib import Path
import argparse
import json
import re
import shutil

from common import ROOT, LOCAL, now, digest, write_json, render_ledger, update_task


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prd", type=Path, required=True)
    args = parser.parse_args()
    execution = ROOT / "HSR_AI_Companion_开发执行顺序_v1.0.md"
    design = ROOT / "HSR_AI_Companion_完整实现规划_v1.0.md"
    for directory in ("docs/requirements", "docs/development", "docs/decisions"):
        (ROOT / directory).mkdir(parents=True, exist_ok=True)
    target = ROOT / "docs/requirements/PRD_v1.md"
    if target.exists() and digest(target) != digest(args.prd):
        raise RuntimeError("Existing PRD differs; refusing to overwrite")
    if not target.exists():
        shutil.copyfile(args.prd, target)
    origin = {"at": now(), "source": str(args.prd.resolve()),
              "copy": str(target.relative_to(ROOT)), "sha256": digest(args.prd),
              "copy_sha256": digest(target),
              "planning_hashes": {p.name: digest(p) for p in (execution, design)}}
    write_json(LOCAL / "evidence/D001/requirements-origin.json", origin)
    write_json(ROOT / "docs/requirements/baseline.json", {
        "prd": "docs/requirements/PRD_v1.md", "sha256": origin["sha256"],
        "source_path_record": ".local/evidence/D001/requirements-origin.json",
        "planning_hashes": origin["planning_hashes"],
        "confirmed_additions": ["仅 Windows", "无交付期限", "本次授权执行 P0"],
    })
    ledger = ROOT / "docs/development/task-status.json"
    if not ledger.exists():
        tasks = []
        chunks = re.split(r"^### (D\d{3})｜([^\n]+)\n", execution.read_text(encoding="utf-8"), flags=re.M)
        for i in range(1, len(chunks), 3):
            task_id, title, body = chunks[i:i+3]
            pre = re.search(r"\*\*前置：\*\*([^\n]+)", body)
            tasks.append({"id": task_id, "title": title.strip(),
                          "dependencies": re.findall(r"D\d{3}", pre.group(1)) if pre else [],
                          "status": "NOT_STARTED", "started_at": None, "completed_at": None,
                          "snapshot": None, "artifacts": [], "commands": [],
                          "test_counts": None, "evidence": [], "blockers": [], "next_step": "待前置完成"})
        assert len(tasks) == 58 and len({t["id"] for t in tasks}) == 58
        write_json(ledger, {"schema_version": 1, "created_at": now(), "tasks": tasks})
        render_ledger(tasks)
    additions = ROOT / "docs/requirements/local-decisions.md"
    if not additions.exists():
        additions.write_text(
            "# 本地补充决定\n\n原始 PRD 不作改写。\n\n"
            "- 规划前已确认：仅支持 Windows；没有交付期限。\n"
            "- 本次用户授权：按开发执行顺序 v1.0 实施 P0（001～009）。\n"
            "- 工程测试优先合成账号；不需要用户真实 UID；不调用额外付费模型。\n"
            "- 本次不对外发布；没有为原创项目决定开源许可证。\n", encoding="utf-8")
    # Mapping is extracted from the agreed execution plan, not invented.
    owner_rows = re.findall(r"^\| (A\d{2}[^|]*) \| ([^|]+) \|$",
                           execution.read_text(encoding="utf-8"), flags=re.M)
    mappings = {}
    for label, owners in owner_rows:
        ids = re.findall(r"A\d{2}", label)
        for aid in ids:
            mappings[aid] = (label.strip(), owners.strip())
    assert set(mappings) == {f"A{i:02}" for i in range(1,25)}
    lines = ["# 需求追踪", "", "最终责任任务沿用开发顺序 12.3 节；P0 只提供选型证据，不等于最终产品验收。", "",
             "| 验收 | 需求组 | 最终责任任务 | 当前验证层次 |", "|---|---|---|---|"]
    for aid, (label, owners) in sorted(mappings.items()):
        lines.append(f"| {aid} | {label} | {owners} | 待执行；P0 证据见阶段关口 |")
    lines += ["", "| 补充 | 责任 |", "|---|---|", "| 仅 Windows | D002、D018、D051 |",
              "| 无交付期限 | 阶段验收驱动推进 |", "| 本次 P0 开发授权 | D001～D009；不自动进入 P1 |"]
    (ROOT / "docs/requirements/traceability.md").write_text("\n".join(lines)+"\n", encoding="utf-8")
    checks = {"task_count": 58, "acceptance_count": len(mappings),
              "prd_hash_equal": digest(target) == digest(args.prd),
              "plans_unchanged": all(digest(ROOT/p) == h for p,h in origin["planning_hashes"].items())}
    assert checks["prd_hash_equal"] and checks["plans_unchanged"]
    write_json(LOCAL / "evidence/D001/validation.json", {"at": now(), "exit_code": 0, "checks": checks})
    update_task("D001", "DONE", summary="原文哈希一致；58 项账本及 24 项追踪已建；原规划未改",
                artifacts=["docs/requirements/PRD_v1.md", "docs/requirements/traceability.md", "docs/development/task-status.md", ".gitignore"],
                commands=["python tools/p0/bootstrap.py --prd <原 PRD 本地路径>"],
                counts={"passed": 4, "failed": 0, "skipped": 0},
                evidence=[".local/evidence/D001/requirements-origin.json", ".local/evidence/D001/validation.json"],
                next_step="D002")
    print(json.dumps(checks, ensure_ascii=False))


if __name__ == "__main__":
    main()
