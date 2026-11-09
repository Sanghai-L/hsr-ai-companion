"""Reproducible measured timings, separated by cold/warm and runtime scope."""
from copy import deepcopy
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time
import uuid

from companion.accounts import AccountService
from companion.contracts import canonical
from companion.knowledge.package import build_package
from companion.release.artifacts import make_artifact, write_release
from companion.release.signing import test_key
from companion.services.context import Context
from companion.services.registry import Registry
from companion.storage import Store
from companion.updates.knowledge import KnowledgeSync
from companion.updates.source import ReleaseSource

ROOT = Path(__file__).resolve().parents[2]


def main():
    label = uuid.uuid4().hex[:10]
    directory = ROOT/".local/evidence/D053"/label
    directory.mkdir(parents=True)
    context = Context(directory/"synthetic-player", offline=True)
    registry = Registry(context)
    sample = json.loads((ROOT/"src/companion/resources/examples/moc-comparison.json").read_bytes())
    damage = json.loads((ROOT/"tests/fixtures/requests/damage.json").read_bytes())
    metrics = {}
    def measure(name, function, n=30):
        samples = []
        for _ in range(n):
            started = time.perf_counter()
            value = function()
            samples.append((time.perf_counter()-started)*1000)
            if hasattr(value, "status"):
                assert value.status == "success", (name, value.error)
        ordered = sorted(samples)
        metrics[name] = {"n": n, "p50_ms": round(statistics.median(samples), 3), "p95_ms": round(ordered[math.ceil(.95*n)-1], 3),
                         "max_ms": round(max(samples), 3), "samples_ms": [round(x, 3) for x in samples]}
    measure("knowledge_search_first", lambda: registry.invoke("knowledge_search", {"query": "拉条 行动提前"}), 1)
    measure("knowledge_search_warm", lambda: registry.invoke("knowledge_search", {"query": "拉条 行动提前"}))
    measure("damage_formula", lambda: registry.invoke("calculate", damage))
    measure("representative_single_comparison", lambda: registry.invoke("simulation_compare", sample))
    batch = deepcopy(sample)
    for i in range(2, 4):
        candidate = deepcopy(batch["request"]["candidates"][i%2])
        candidate["id"] = "batch-"+str(i)
        batch["request"]["candidates"].append(candidate)
    batch["request"]["budget"].update(max_candidates=4, max_actions=100)
    measure("representative_batch_four", lambda: registry.invoke("simulation_compare", batch), 20)
    AccountService(context.store).configure("perf-synthetic", style="A", region="ASIA")
    measure("account_read", lambda: registry.invoke("account_get", {"account_id": "perf-synthetic"}))
    measure("account_write", lambda: registry.invoke("account_configure", {"account_id": "perf-synthetic", "style": "A", "region": "ASIA"}))
    private, public = test_key()
    package = build_package(ROOT/"knowledge", version="0.2.1")
    write_release(directory/"source", make_artifact({"package.json": package.encode()}, kind="knowledge", version="0.2.1", private=private), "knowledge.TEST.json", private)
    source = ReleaseSource(directory/"source", trusted_keys=[public], require_signature=True, allow_test=True)
    count = [0]
    def sync():
        count[0] += 1
        return KnowledgeSync(directory/str(count[0]), source=source).sync(force=True)
    measure("knowledge_signed_local_sync_cold", sync, 10)
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    def cold():
        result = subprocess.run([sys.executable, "-m", "companion", "--data-dir", str(directory/"cold"), "--offline", "call", "knowledge_search", "--input", "-"],
                                input=canonical({"query": "拉条"}), capture_output=True, env=env, timeout=10)
        assert result.returncode == 0, result.stderr
    measure("knowledge_cli_cold_process", cold, 10)
    from tests.simulation.test_backend_adapter import installed_backend, legacy_input
    backend = installed_backend()
    measure("optional_legacy_single", lambda: backend.execute(legacy_input("team-a")), 5)
    measure("optional_legacy_batch_two", lambda: [backend.execute(legacy_input(t)) for t in ("team-a", "team-b")], 3)
    result = {"at": datetime.now(timezone.utc).isoformat(), "platform": platform.platform(), "machine": platform.machine(),
              "python": platform.python_version(), "scope": "actual local Windows machine; tool timing excludes host model latency; optional legacy backend remains separate",
              "metrics": metrics, "raw_directory": str(directory), "network_requests": 0,
              "initial_one_second_target": all(metrics[k]["p95_ms"] < 1000 for k in ("knowledge_search_warm", "damage_formula", "knowledge_cli_cold_process"))}
    (directory/"performance.json").write_bytes(canonical(result))
    print(json.dumps({"evidence": str(directory/"performance.json"), "one_second_target": result["initial_one_second_target"], "metrics": {k:{m:v for m,v in row.items() if m!="samples_ms"} for k,row in metrics.items()}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
