import json
import subprocess
import sys

import pytest

from companion.accounts import AccountService
from companion.contracts import CompanionError
from companion.memory.append import MemoryAppend
from companion.memory.search import MemorySearch
from companion.services.context import Context
from companion.services.registry import Registry
from companion.session.context import select_context
from companion.storage import Store


@pytest.fixture
def rig(tmp_path):
    store = Store(tmp_path)
    AccountService(store).configure("a", style="A")
    AccountService(store).configure("b", style="B")
    return store, MemoryAppend(store), MemorySearch(store)


def conclusion(append, account="a", **kwargs):
    defaults = {"topic": "黄泉叠层", "entities": ["1308:base"], "game_version": "4.6", "claim_key": "acheron-stacks",
                "conditions": ["每次施放技能"], "source_refs": ["knowledge:debuff-once"]}
    defaults.update(kwargs)
    return append.append(account, "conclusion", "黄泉叠层条件", "多段不直接等于多层。", "记录按技能次数判断。", **defaults)


def test_restart_account_version_filter_and_long_body_reference(rig):
    store, append, search = rig
    a = conclusion(append).data["research_id"]
    conclusion(append, "b")
    conclusion(append, game_version="4.5")
    result = search.search("a", query="叠层", game_version="4.6", entities=["1308:base"])
    assert [i["research_id"] for i in result.data["items"]] == [a]
    assert result.data["items"][0]["body_ref"] == "memory_read:" + a
    assert search.search("a", game_version="9.0").data["items"] == []
    code = "import json,sys;from companion.storage import Store;from companion.memory.search import MemorySearch;print(json.dumps(MemorySearch(Store(sys.argv[1],read_only=True)).search('a',game_version='4.6').to_dict()))"
    process = subprocess.run([sys.executable, "-c", code, str(store.files.root)], capture_output=True, text=True, encoding="utf-8", timeout=15)
    assert process.returncode == 0, process.stderr
    assert json.loads(process.stdout)["data"]["items"][0]["research_id"] == a
    with pytest.raises(CompanionError):
        search.read("b", a)


def test_hypothesis_never_updates_account_facts_and_context_is_bounded(rig):
    store, append, search = rig
    for index in range(8):
        append.append("a", "hypothesis", f"假设 {index}", "长正文" * 3000, "尚未验证的假设。" * 70, topic="配队", game_version="4.6")
    assert store.latest_snapshot("a") is None
    result = select_context(store, "a", char_budget=1800)
    assert result.data["chars_used"] <= 1800 and result.data["truncated"]
    assert all(item["record_type"] == "hypothesis" for item in result.data["items"])
    first = search.search("a").data["items"][0]
    body = search.read("a", first["research_id"], limit=20)
    assert len(body.data["content"]) == 20 and body.data["next_offset"] == 20


def test_same_claim_cannot_replace_via_append_and_unknown_experiment_rejected(rig):
    store, append, search = rig
    first = conclusion(append)
    assert conclusion(append).data["state"] == "duplicate"
    with pytest.raises(CompanionError) as error:
        append.append("a", "conclusion", "new", "改成相反结论", "new", topic="黄泉叠层", entities=["1308:base"], game_version="4.6",
                      claim_key="acheron-stacks", conditions=["另一条件"], source_refs=["user:new evidence"])
    assert error.value.code == "CONFLICT"
    assert search.search("a").data["total"] == 1
    with pytest.raises(CompanionError):
        conclusion(append, game_version="4.7", experiment_ids=["unknown"])


def test_registry_rejects_hidden_revision_metadata_and_fact_without_basis(tmp_path):
    registry = Registry(Context(tmp_path, offline=True))
    registry.invoke("account_configure", {"account_id": "a"})
    value = {"account_id": "a", "record_type": "hypothesis", "title": "test", "body": "body", "summary": "summary", "topic": "test"}
    assert registry.invoke("memory_append", {**value, "revision_of": "old"}).error["code"] == "INVALID_INPUT"
    assert registry.invoke("memory_append", {**value, "record_type": "fact"}).error["code"] == "INVALID_INPUT"
    assert registry.invoke("memory_append", value).status == "success"
    assert registry.invoke("session_bootstrap", {}).data["memory"]["data"]["items"]


def test_damaged_body_is_not_returned_as_intact_summary(rig):
    store, append, search = rig
    rid = conclusion(append).data["research_id"]
    store.files.path(f"research/a/{rid}.md").write_text("tampered", encoding="utf-8")
    with pytest.raises(CompanionError):
        search.search("a")
    assert store.recover_research()["damaged"]


def test_large_metadata_pages_before_transport_limit(tmp_path):
    context = Context(tmp_path, offline=True)
    AccountService(context.store).configure("a")
    for i in range(5):
        MemoryAppend(context.store).append("a", "discussion", str(i), "正文" * 10000, "摘要" * 700, topic="long",
            source_refs=["https://example.com/" + "a"*1800 for _ in range(8)])
    registry = Registry(context)
    first = registry.invoke("memory_search", {"account_id": "a", "limit": 20})
    assert first.status == "success" and first.data["next_offset"] is not None
    found = set()
    offset = 0
    while offset is not None:
        page = registry.invoke("memory_search", {"account_id": "a", "limit": 20, "offset": offset})
        assert page.status == "success"
        found.update(x["research_id"] for x in page.data["items"])
        offset = page.data["next_offset"]
    assert len(found) == 5
    read = registry.invoke("memory_read", {"account_id": "a", "research_id": next(iter(found)), "limit": 12000})
    assert read.status == "success"
