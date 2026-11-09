import io

import pytest

from companion.contracts import CompanionError
from companion.policy import ConsentPolicy
from companion.policy.consent import binding
from companion.storage import Store
from companion.updates.program import ProgramUpdates


def setup(tmp_path):
    store = Store(tmp_path / "personal")
    updates = ProgramUpdates(store, "C:/Program/companion")
    plan = updates.propose({"version": "0.2.0", "sha256": "a" * 64})
    return store, updates, plan, ConsentPolicy(store)


def receipt(plan):
    return {"source_kind": "host_native", "source_ref": "synthetic-user-message-1",
            "host_permission": "approved", "decision": "approve", "binding_sha256": binding(plan)}


def test_no_confirmation_and_boolean_self_approval_rejected(tmp_path):
    _, _, plan, policy = setup(tmp_path)
    with pytest.raises(CompanionError):
        policy.consume(plan["id"], package_sha256="a" * 64, scope_path=plan["scope_path"])
    with pytest.raises(CompanionError):
        policy.record_verified(plan["id"], {"confirmed": True})
    with pytest.raises(CompanionError):
        policy.record_verified(plan["id"], receipt(plan))
    with pytest.raises(CompanionError):
        policy.confirm_terminal(plan["id"], stdin=io.StringIO("yes"), stdout=io.StringIO())


def test_confirmation_is_one_shot_and_bound_to_package_and_scope(tmp_path):
    _, _, plan, policy = setup(tmp_path)
    proof = receipt(plan)
    policy.record_verified(plan["id"], proof, verifier=lambda supplied, digest: supplied is proof and digest == binding(plan))
    for package, scope in [("b" * 64, plan["scope_path"]), ("a" * 64, "C:/elsewhere")]:
        with pytest.raises(CompanionError):
            policy.consume(plan["id"], package_sha256=package, scope_path=scope)
    assert policy.consume(plan["id"], package_sha256="a" * 64, scope_path=plan["scope_path"])["target_version"] == "0.2.0"
    with pytest.raises(CompanionError):
        policy.consume(plan["id"], package_sha256="a" * 64, scope_path=plan["scope_path"])


def test_package_changed_invalidates_old_confirmation(tmp_path):
    _, updates, plan, policy = setup(tmp_path)
    policy.record_verified(plan["id"], receipt(plan), verifier=lambda *_: True)
    changed = updates.propose({"version": "0.2.0", "sha256": "b" * 64})
    assert changed["id"] != plan["id"]
    with pytest.raises(CompanionError):
        policy.consume(plan["id"], package_sha256="a" * 64, scope_path=plan["scope_path"])


def test_confirmation_cannot_be_used_for_another_plan(tmp_path):
    _, updates, plan, policy = setup(tmp_path)
    other = updates.propose({"version": "0.3.0", "sha256": "b" * 64})
    with pytest.raises(CompanionError):
        policy.record_verified(other["id"], receipt(plan), verifier=lambda *_: True)

