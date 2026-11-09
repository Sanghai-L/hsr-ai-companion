import json

import pytest

from companion.contracts import CompanionError, canonical
from companion.install import Installer
from companion.policy import ConsentPolicy
from companion.policy.consent import binding
from companion.release.artifacts import make_artifact, write_release
from companion.release.signing import test_key as new_key
from companion.storage import Store
from companion.updates.program import ProgramUpdates
from companion.updates.source import ReleaseSource


def test_signed_source_apply_is_bound_and_consumes_real_receipt(tmp_path, monkeypatch):
    private, public = new_key()
    source_dir = tmp_path/"maintainer"
    data = tmp_path/"player"
    store = Store(data/"personal")
    root = tmp_path/"app"
    monkeypatch.setattr(Installer, "_health_check", lambda self, version, candidate: {"status": "PASS", "version": (version/"runtime/python.exe").read_text()})
    def package(version):
        return make_artifact({"runtime/python.exe": version.encode()}, kind="program", version=version, private=private)
    Installer(root, data, trusted_keys=[public], allow_test=True).install(package("0.1.2"))
    write_release(source_dir, package("0.1.3"), "program.json", private)
    source = ReleaseSource(source_dir, trusted_keys=[public], require_signature=True, allow_test=True)
    updates = ProgramUpdates(store, root, source=source, current_version="0.1.2")
    plan = updates.check(force=True).data["plan"]
    with pytest.raises(CompanionError):
        updates.apply(plan["id"], "invented")
    proof = {"source_kind": "host_native", "source_ref": "synthetic-integration-test", "host_permission": "approved",
             "decision": "approve", "binding_sha256": binding(plan)}
    reference = ConsentPolicy(store).record_verified(plan["id"], proof, verifier=lambda received, expected: received is proof and expected == binding(plan))
    result = updates.apply(plan["id"], reference, offline=True)
    assert result.data["installed"] and result.data["version"] == "0.1.3"
    with store.connection() as connection:
        assert connection.execute("SELECT consumed_at FROM confirmations WHERE id=?", (reference,)).fetchone()[0]
    with pytest.raises(CompanionError):
        updates.apply(plan["id"], reference)


def test_production_source_rejects_unsigned_index_and_unknown_signer(tmp_path):
    private, public = new_key()
    write_release(tmp_path, make_artifact({"runtime/python.exe": b"exe"}, kind="program", version="0.1.3", private=private), "program.json", private)
    for keys, allow_test in [([], True), ([public], False)]:
        with pytest.raises(CompanionError):
            ReleaseSource(tmp_path, trusted_keys=keys, require_signature=True, allow_test=allow_test).manifest("program")
    index = json.loads((tmp_path/"release.json").read_bytes())["release"]
    (tmp_path/"release.json").write_bytes(canonical({k:v for k,v in index.items() if k not in {"channel", "content_sha256"}}))
    with pytest.raises(CompanionError):
        ReleaseSource(tmp_path, trusted_keys=[public], require_signature=True).manifest("program")
