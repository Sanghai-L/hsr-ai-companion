"""Run relevant upstream tests with explicit offline and process guards."""
import os
from pathlib import Path
import platform
import sys
import time

import pytest

ROOT = Path(__file__).resolve().parents[2]
REPO = ROOT / ".local/upstream/hsr-nous/repo"


def offline_audit(event, args):
    # Upstream Monte Carlo metadata reads its own Git SHA. This read-only
    # subprocess is expected; arbitrary executables/services remain forbidden.
    if event == "subprocess.Popen" and args[1] == "git rev-parse HEAD" and Path(args[2]).resolve() == REPO.resolve():
        return
    if event in {"socket.connect", "socket.getaddrinfo", "subprocess.Popen", "os.system"}:
        raise RuntimeError("P0 offline core tests forbid network/process launch: " + event)


if __name__ == "__main__":
    os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    os.environ["HSR_NOUS_DATA_DIR"] = str(ROOT / ".local/data-snapshot")
    # pytest asks Windows for its version when building its session header.
    # Prime that standard-library cache before guarding the actual test run.
    platform.platform()
    platform.uname()
    temp = ROOT / ".local/probes/test-temp/中文 空格" / str(time.time_ns())
    temp.parent.mkdir(parents=True, exist_ok=True)
    sys.addaudithook(offline_audit)
    os.chdir(REPO)
    sys.path.insert(0, str(REPO/"tests"))
    raise SystemExit(pytest.main([
        "tests/test_engine_v01.py", "tests/test_engine_v02.py", "tests/test_compile.py",
        "tests/test_expression.py", "tests/test_cycle_v11.py", "tests/test_caveats_channel.py",
        "tests/test_save_restore.py", "tests/test_phainon_template_e2e.py",
        str(ROOT/"tests/p0/test_simulator_budget.py"),
        # Explicit scope: a FastAPI web presentation test belongs to an optional
        # component deliberately not installed for a simulation-core probe.
        "-k", "not test_web_state_payload_caveats",
        "-q", "-ra", "--basetemp", str(temp),
        "-o", "cache_dir="+str(ROOT/".local/cache/pytest/core"),
        "--junitxml", str(ROOT/".local/evidence/D008/core-tests.xml"),
    ]))
