"""Workspace-local temp files and immutable, labelled pytest evidence."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[2]
GROUPS = {
    "p4": ["tests/simulation", "tests/jobs", "tests/modes/test_moc.py", "tests/experiments", "tests/planning"],
    "p5": ["tests/modes", "tests/simulation", "tests/jobs", "tests/planning", "tests/sources/test_current_stages.py", "tests/experiments/test_representative_replay.py"],
    "all": ["tests", "--ignore=tests/p0", "-m", "not live"],
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--group", choices=GROUPS, default="p5")
    args = parser.parse_args()
    label = args.group + "-" + uuid.uuid4().hex[:10]
    evidence = ROOT / (".local/evidence/D042" if args.group == "p4" else ".local/evidence/D049")
    evidence.mkdir(parents=True, exist_ok=True)
    temp = ROOT / ".local/tmp/p5" / label
    temp.mkdir(parents=True)
    environment = os.environ.copy()
    environment.update(TEMP=str(temp), TMP=str(temp), PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    command = [sys.executable, "-m", "pytest", *GROUPS[args.group], "-q", "-ra", "--tb=short", "--junitxml=" + str(evidence / (label + ".xml"))]
    process = subprocess.run(command, cwd=ROOT, env=environment, text=True, encoding="utf-8", capture_output=True)
    record = {"at": datetime.now(timezone.utc).isoformat(), "command": command, "cwd": str(ROOT),
              "exit_code": process.returncode, "stdout": process.stdout, "stderr": process.stderr}
    (evidence / (label + ".json")).write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    print(process.stdout + process.stderr)
    print("Evidence: " + str(evidence / (label + ".json")))
    return process.returncode


if __name__ == "__main__":
    raise SystemExit(main())
