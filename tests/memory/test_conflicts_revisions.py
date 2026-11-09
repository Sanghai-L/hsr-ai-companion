import io
import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from companion.accounts import AccountService
from companion.contracts import CompanionError
from companion.memory.append import MemoryAppend
from companion.memory.conflicts import Conflicts
from companion.memory.revisions import Revisions
from companion.memory.search import MemorySearch
from companion.sources.evidence import EvidenceService
from companion.storage import Store


@pytest.fixture
def rig(tmp_path):
    store = Store(tmp_path)
    AccountService(store).configure("a")
    AccountService(store).configure("b")
    rid = MemoryAppend(store).append("a", "conclusion", "旧研究", "旧正文", "旧摘要", topic="命题", claim_key="claim",
                                   game_version="4.6", conditions=["原条件"], source_refs=["user:original discussion"]).data["research_id"]
    eid = EvidenceService(store).register("a", "命题", "https://example.com/new", "新证据", kind="host_page", stance="opposes").data["registered_id"]
    return store, rid, eid


def propose(rig, action="replace", conditions=None):
    store, rid, eid = rig
    return Conflicts(store).propose("a", rid, [eid], "出现新反例", "新正文", "新摘要", action=action, conditions=conditions).data


def confirm(store, proposal, ref="actual-test-user-turn"):
    receipt = {"source_kind": "host_native", "source_ref": ref, "reply_text": "确认这份具体修订", "decision": "approve", "binding_sha256": proposal["binding_sha256"]}
    return Revisions(store).record_verified("a", proposal["plan_id"], receipt,
        verifier=lambda supplied, digest: supplied is receipt and digest == receipt["binding_sha256"])


def test_unanswered_conflict_preserves_old_text_and_is_retrievable(rig):
    store, rid, eid = rig
    proposal = propose(rig)
    assert store.read_research("a", rid) == "旧正文"
    item = MemorySearch(store).search("a").data["items"][0]
    assert item["research_id"] == rid and item["pending_conflicts"][0]["evidence_ids"] == [eid]
    with pytest.raises(CompanionError) as error:
        Revisions(store).apply("a", proposal["plan_id"], rid, "model-says-confirmed")
    assert error.value.code == "CONFIRMATION_REQUIRED"
    fake = {"source_kind": "host_native", "source_ref": "user:invented", "reply_text": "yes", "decision": "approve", "binding_sha256": proposal["binding_sha256"]}
    with pytest.raises(CompanionError):
        Revisions(store).record_verified("a", proposal["plan_id"], fake)
    with pytest.raises(CompanionError):
        Revisions(store).confirm_terminal("a", proposal["plan_id"], stdin=io.StringIO("yes\n"), stdout=io.StringIO())


@pytest.mark.parametrize("action", ["replace", "restrict", "retract"])
def test_confirmed_revision_history_idempotence_and_scope(rig, action):
    store, rid, _ = rig
    proposal = propose(rig, action=action, conditions=["新增限制"] if action == "restrict" else None)
    consent = confirm(store, proposal)
    applied = Revisions(store).apply("a", proposal["plan_id"], rid, consent)
    new_id = applied.data["research_id"]
    assert store.read_research("a", rid) == "旧正文"
    assert store.read_research("a", new_id) == "新正文"
    assert Revisions(store).apply("a", proposal["plan_id"], rid, consent).data["idempotent"]
    result = MemorySearch(store).search("a").data["items"]
    assert len(result) == (0 if action == "retract" else 1)
    if result:
        assert result[0]["research_id"] == new_id and result[0]["revision"] == 2 and not result[0]["pending_conflicts"]
    assert not MemorySearch(store).read("a", rid).data["is_current"]
    with pytest.raises(CompanionError):
        Revisions(store).apply("b", proposal["plan_id"], rid, consent)


def test_old_version_and_parallel_duplicate_confirmation(rig):
    store, rid, _ = rig
    p1, p2 = propose(rig), propose(rig)
    c1, c2 = confirm(store, p1, "user:1"), confirm(store, p2, "user:2")
    def apply():
        return Revisions(store).apply("a", p1["plan_id"], rid, c1)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: apply(), range(2)))
    assert len({r.data["research_id"] for r in results}) == 1
    with pytest.raises(CompanionError) as error:
        Revisions(store).apply("a", p2["plan_id"], rid, c2)
    assert error.value.code == "CONFLICT"


def test_tampered_plan_invalidates_confirmation(rig):
    store, rid, _ = rig
    proposal = propose(rig)
    consent = confirm(store, proposal)
    with store.transaction() as connection:
        row = connection.execute("SELECT payload FROM revision_plans WHERE id=?", (proposal["plan_id"],)).fetchone()
        payload = json.loads(row["payload"])
        payload["new_body"] = "tampered"
        connection.execute("UPDATE revision_plans SET payload=? WHERE id=?", (json.dumps(payload), proposal["plan_id"]))
    with pytest.raises(CompanionError):
        Revisions(store).apply("a", proposal["plan_id"], rid, consent)


def test_staged_revision_recovery_does_not_change_head(rig):
    store, rid, _ = rig
    # Simulate the immutable file/index phase before the head commit.
    old_meta = MemorySearch(store).read("a", rid).data["metadata"]
    staged = store.create_research("a", "staged", "not approved", metadata={**old_meta, "revision_of": rid})
    assert store.recover_research() == {"recovered": [], "damaged": [], "missing": []}
    assert MemorySearch(store).search("a").data["items"][0]["research_id"] == rid
