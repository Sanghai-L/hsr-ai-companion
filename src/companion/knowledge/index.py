"""Rebuildable, content-bound Chinese character/term inverted index."""
from collections import Counter
import hashlib
import json
import re
import unicodedata

from companion.contracts import canonical

INDEX_VERSION = 1


def normalize(text):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text).casefold())


def tokens(text):
    normalized = normalize(text)
    terms = re.findall(r"[a-z0-9_]+|[\u3400-\u9fff]", normalized)
    for run in re.findall(r"[\u3400-\u9fff]+", normalized):
        terms += [run[i:i+2] for i in range(len(run)-1)]
    return terms


def build_index(package):
    documents, postings = {}, {}
    for entry in package.manifest["entries"]:
        # Bibliography URLs should not become keyword hits.
        body = package.bodies[entry["body_path"]].split("\n来源：", 1)[0]
        counts = Counter(tokens(entry["title"] + " " + " ".join(entry["aliases"]) + " " + body))
        documents[entry["id"]] = {"length": sum(counts.values()), "terms": dict(sorted(counts.items()))}
        for term, count in counts.items():
            postings.setdefault(term, {})[entry["id"]] = count
    return {"index_version": INDEX_VERSION, "package_sha256": package.fingerprint,
            "documents": documents, "postings": postings}


def ensure_index(package, files, relative):
    expected = build_index(package)
    path = files.path(relative)
    try:
        actual = json.loads(path.read_bytes())
    except (OSError, ValueError):
        actual = None
    if actual != expected:
        files.write(relative, canonical(expected))
    return expected
