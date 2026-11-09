"""Check shipped command names and local documentation links without changing player data."""
import json
from pathlib import Path
import re
import subprocess
import sys

from companion import __version__
from companion.contracts import canonical
from companion.services.context import Context
from companion.services.registry import Registry

ROOT = Path(__file__).resolve().parents[2]


def main():
    checks = []
    for command in ("diagnostics-plan", "diagnostics-export", "install-program", "configure-codex", "recover-program", "rollback-program", "uninstall-program", "confirm-update", "confirm-revision"):
        result = subprocess.run([sys.executable, "-m", "companion", command, "--help"], capture_output=True, timeout=15)
        assert result.returncode == 0, command
        checks.append("CLI:"+command)
    registry = Registry(Context(ROOT/".local/evidence/D055/untouched-doc-check", offline=True))
    for kind in ("damage", "timeline", "gacha", "pull_plan"):
        sample = registry.invoke("calculation_schema", {"kind": kind}).data["example_request"]
        result = registry.invoke("plan_pulls" if kind == "pull_plan" else "calculate", sample)
        assert result.status == "success", kind
        checks.append("example:"+kind)
    for name in ("README.md", "INSTALL_AGENT.md", "CONTRIBUTING.md"):
        text = (ROOT/name).read_text(encoding="utf-8")
        for target in re.findall(r"\]\(([^)]+)\)", text):
            if not target.startswith("https://"):
                assert (ROOT/target).is_file(), (name, target)
        checks.append("links:"+name)
    assert __version__ in (ROOT/"README.md").read_text(encoding="utf-8")
    assert not (ROOT/".local/evidence/D055/untouched-doc-check").exists()
    report = {"status": "PASS", "checks": checks, "passed": len(checks), "player_data_created": False, "network": False}
    target = ROOT/".local/evidence/D055/docs.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(canonical(report))
    print(json.dumps(report))


if __name__ == "__main__":
    main()
