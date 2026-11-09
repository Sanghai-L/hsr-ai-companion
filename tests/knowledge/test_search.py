import copy
import hashlib
import json
from pathlib import Path

import pytest

from companion.contracts import CompanionError
from companion.knowledge.index import build_index, ensure_index
from companion.knowledge.package import build_package
from companion.knowledge.search import KnowledgeSearch
from companion.storage import SafeRoot

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def search():
    return KnowledgeSearch(build_package(ROOT / "knowledge", version="0.2.0"))


def test_frozen_validation_retrieval_top5(search):
    dataset = json.loads((ROOT / "evals/retrieval/queries.json").read_bytes())
    scores = {}
    for split in ("development", "validation"):
        queries = [q for q in dataset["queries"] if q["split"] == split]
        misses = []
        for query in queries:
            items = search.search(query["query"], version=query["version"]).data["items"]
            if not set(query["relevant_ids"]) & {i["id"] for i in items}:
                misses.append(query["id"])
        scores[split] = {"count": len(queries), "hits": len(queries)-len(misses), "misses": misses}
    assert scores["validation"]["hits"] / scores["validation"]["count"] >= .9, scores
    assert scores["development"]["hits"] / scores["development"]["count"] >= .9, scores


def test_form_disambiguation_and_version_filter(search):
    assert search.search("三月七", version="4.6").data["ambiguities"][0]["needs_clarification"]
    assert not search.search("三月七存护", version="4.6").data["ambiguities"]
    assert search.search("三月七不是巡猎是冰盾", version="4.6").data["items"][0]["id"] == "march-preservation"
    assert search.search("白厄", version="4.5").data["items"] == []
    assert search.search("白厄", version="9.9").data["items"] == []
    with pytest.raises(CompanionError):
        search.search("白厄", version="latest")


def test_namespace_and_source_pagination(search):
    package = copy.deepcopy(search.package)
    e = package.manifest["entries"][0]
    e.update(namespace="beta", information_state="beta")
    modified = KnowledgeSearch(package)
    assert all(i["id"] != e["id"] for i in modified.search(e["title"], limit=20).data["items"])
    assert modified.search(e["title"], namespace="beta").data["items"][0]["id"] == e["id"]
    with pytest.raises(CompanionError):
        search.search("白厄", information_state="beta")
    first = search.read("forms", limit=20, source_limit=1)
    second = search.read("forms", offset=first.data["next_offset"], source_offset=first.data["next_source_offset"], source_limit=1)
    assert len(first.sources) == len(second.sources) == 1
    assert first.sources != second.sources
    assert first.data["content"] + second.data["content"] == search.package.bodies[search.entries["forms"]["body_path"]][:4020]


def test_index_rebuild_from_corrupt_old_version_and_new_package(search, tmp_path):
    files = SafeRoot(tmp_path)
    index = ensure_index(search.package, files, "index.json")
    files.write("index.json", b'{"index_version":0}')
    assert ensure_index(search.package, files, "index.json") == index
    files.write("index.json", b'broken')
    assert ensure_index(search.package, files, "index.json") == build_index(search.package)
