"""Actual embedded-runtime install/upgrade/recovery; synthetic future version only."""
from pathlib import Path
import argparse
import json
import os
import subprocess
import uuid

from companion.accounts import AccountService
from companion.contracts import canonical
from companion.install import Installer
from companion.policy import ConsentPolicy
from companion.policy.consent import binding
from companion.release.artifacts import make_artifact, open_artifact, write_release
from companion.release.signing import load_trust, test_key
from companion.storage import Store
from companion.updates.program import ProgramUpdates
from companion.updates.source import ReleaseSource
from tools.p6.record import record, write

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", type=Path, default=ROOT/".local/dist/D051/program/hsr-companion-0.1.3-windows-x64.json")
    args = parser.parse_args()
    label = uuid.uuid4().hex[:10]
    target = ROOT/".local/probes/p6-install"/label
    evidence = ROOT/".local/evidence/D051"/label
    evidence.mkdir(parents=True)
    package = args.artifact
    _, files, _ = open_artifact(package.read_bytes(), load_trust(ROOT/".local/signing/trust.json"))
    private, public = test_key()
    first = make_artifact(files, kind="program", version="0.1.3", private=private)
    data = target/"个人 资料"
    manager = Installer(target/"独立 中文 程序", data, trusted_keys=[public], allow_test=True)
    results = [manager.install(first), manager.install(first)]
    store = Store(data/"personal")
    AccountService(store).configure("p6-synthetic", style="A", region="ASIA")
    research = store.create_research("p6-synthetic", "安装演练", "升级后仍应保留的合成研究")
    def execute(name, arguments, input=None):
        python = manager.root/"versions"/manager.state()["current"]["digest"]/"runtime/python.exe"
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        env["PATH"] = str(Path(os.environ["SystemRoot"])/"System32")
        env.update(PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
        env["HSR_COMPANION_INSTALL_ROOT"] = str(manager.root)
        completed = subprocess.run([str(python), "-I", "-m", "companion", "--data-dir", str(data), "--offline", *arguments],
                                   cwd=target, env=env, input=canonical(input) if input is not None else None, capture_output=True, timeout=30)
        item = {"name": name, "exit_code": completed.returncode, "stdout": completed.stdout.decode("utf-8", "replace"), "stderr": completed.stderr.decode("utf-8", "replace"),
                "python": str(python), "path_only_system32": True}
        results.append(item)
        write(evidence.relative_to(ROOT)/"progress.json", {"target": str(target), "results": results})
        assert completed.returncode == 0, item
        return json.loads(completed.stdout)
    execute("first-doctor", ["doctor", "--json"])
    execute("first-status", ["status", "--json"])
    schema = execute("analysis-schema", ["call", "analysis_schema", "--input", "-"], {})
    sample = schema["data"]["example_request"]["request"]
    saved = execute("saved-before-upgrade", ["call", "comparison_save", "--input", "-"], {"account_id": "p6-synthetic", "request": sample})
    experiment_id = saved["data"]["experiment_id"]
    # The next version is synthetic, signed by a TEST key in this isolated installation only.
    path = "runtime/Lib/site-packages/companion/__init__.py"
    files[path] = files[path].replace(b'"0.1.3"', b'"0.1.4"')
    next_package = make_artifact(files, kind="program", version="0.1.4", private=private)
    source_dir = evidence/"synthetic-source"
    write_release(source_dir, next_package, "synthetic.TEST.json", private)
    source = ReleaseSource(source_dir, trusted_keys=[public], require_signature=True, allow_test=True)
    updates = ProgramUpdates(store, manager.root, source=source, current_version="0.1.3")
    plan = updates.check(force=True).data["plan"]
    receipt = {"source_kind": "host_native", "source_ref": "explicit-synthetic-install-harness", "host_permission": "approved", "decision": "approve", "binding_sha256": binding(plan)}
    confirmation = ConsentPolicy(store).record_verified(plan["id"], receipt, verifier=lambda value, expected: value is receipt and expected == binding(plan))
    results.append(updates.apply(plan["id"], confirmation, offline=True).to_dict())
    assert execute("upgraded-doctor", ["doctor", "--json"])["versions"]["engine"] == "0.1.4"
    replayed = execute("original-snapshot-replay", ["call", "experiment_replay", "--input", "-"], {"account_id": "p6-synthetic", "experiment_id": experiment_id})
    assert replayed["data"]["same_result"] and replayed["data"]["archived_program"]["version"] == "0.1.3"
    results.append(manager.rollback())
    assert execute("rollback-doctor", ["doctor", "--json"])["versions"]["engine"] == "0.1.3"
    assert store.read_research("p6-synthetic", research) == "升级后仍应保留的合成研究"
    results.append(manager.uninstall())
    assert store.read_research("p6-synthetic", research)
    report = {"status": "PASS", "target": str(target), "results": results, "global_python_used_by_installed_app": False,
              "test_layer": "actual PSF embedded runtime and signed synthetic next-version upgrade; separate ordinary Windows directories, not VM",
              "synthetic_confirmation": True, "real_player_queries": 0}
    write(evidence.relative_to(ROOT)/"result.json", report)
    print(json.dumps({"status": "PASS", "evidence": str(evidence/"result.json"), "steps": len(results)}))


if __name__ == "__main__":
    main()
