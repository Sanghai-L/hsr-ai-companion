"""Local evidence retrieval, separate from answer generation and source trust."""
import math
import re

from companion.contracts import CompanionError, ErrorCode, ToolResult
from .index import build_index, normalize, tokens


def game_version(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d+\.\d+(?:\.\d+)?", value):
        raise CompanionError(ErrorCode.INVALID_INPUT, "游戏版本须为 x.y 或 x.y.z")
    return tuple(int(x) for x in value.split(".")) + ((0,) if value.count(".") == 1 else ())


class KnowledgeSearch:
    def __init__(self, package, *, index=None):
        self.package = package
        self.index = index if index is not None else build_index(package)
        self.entries = {e["id"]: e for e in package.manifest["entries"]}

    def search(self, query, *, version=None, namespace="release", information_state=None, limit=5, offset=0):
        if not isinstance(query, str) or not query.strip() or len(query) > 500 or not 1 <= limit <= 20 or offset < 0:
            raise CompanionError(ErrorCode.INVALID_INPUT, "查询为空或检索范围超限")
        if namespace not in {"release", "beta", "leak"}:
            raise CompanionError(ErrorCode.INVALID_INPUT, "知识命名空间无效")
        if information_state in {"beta", "leak"} and namespace != information_state:
            raise CompanionError(ErrorCode.INVALID_INPUT, "未上线信息须显式指定相应命名空间")
        selected_version = game_version(version) if version else None
        query_normalized = normalize(query)
        # In explicit corrective wording, the phrase after “是” identifies the requested form.
        positive = re.sub(r"不是[^是，。]{1,40}是", "", query_normalized)
        query_terms = set(tokens(positive))
        doc_count = max(len(self.entries), 1)
        scores = []
        for key, entry in self.entries.items():
            if entry.get("namespace", "release") != namespace:
                continue
            if information_state is not None and entry["information_state"] != information_state:
                continue
            if namespace == "release" and entry["information_state"] in {"beta", "leak"}:
                continue
            if selected_version and not game_version(entry["version_min"]) <= selected_version <= game_version(entry["version_max"]):
                continue
            doc = self.index["documents"][key]
            score = 0.0
            for term in query_terms:
                count = doc["terms"].get(term, 0)
                if count:
                    frequency = len(self.index["postings"].get(term, {}))
                    score += (2 if len(term) > 1 else .15) * math.log(1 + doc_count / (1 + frequency)) * count / (count + 1)
            for alias in [entry["title"], *entry["aliases"]]:
                normalized_alias = normalize(alias)
                if normalized_alias and normalized_alias in positive:
                    score += 2 + min(len(normalized_alias), 8)
            if score > 0:
                scores.append((score, key))
        scores.sort(key=lambda row: (-row[0], row[1]))
        hits = []
        for score, key in scores[offset:offset + limit]:
            entry = self.entries[key]
            body = self.package.bodies[entry["body_path"]]
            hits.append({"id": key, "title": entry["title"], "score": round(score, 4), "excerpt": body[:450],
                         "version_min": entry["version_min"], "version_max": entry["version_max"],
                         "namespace": entry.get("namespace", "release"), "information_state": entry["information_state"],
                         "evidence": entry["evidence"], "sources": entry["sources"], "conditions": entry["conditions"],
                         "exceptions": entry["exceptions"]})
        ambiguity = []
        if "三月七" in query_normalized and not any(x in positive for x in ("巡猎", "存护", "冰盾", "冰三月", "剑三月")):
            ambiguity = [{"entity": "三月七", "choices": ["1001:preservation", "1224:hunt"], "needs_clarification": True}]
        sources = []
        seen = set()
        for hit in hits:
            for source in hit["sources"]:
                if source["ref"] not in seen:
                    sources.append(source)
                    seen.add(source["ref"])
        return ToolResult(data={"items": hits, "total": len(scores), "next_offset": offset + limit if offset + limit < len(scores) else None,
                                "ambiguities": ambiguity, "version_filter": version, "namespace": namespace}, sources=sources,
                          versions={"knowledge": self.package.manifest["version"]},
                          warnings=(["未指定游戏版本；结果各自保留适用版本，不能视为最新"] if version is None else []) +
                                   (["未正式上线资料，不能用于正式服既成事实"] if namespace != "release" else []))

    def read(self, entry_id, *, offset=0, limit=4000, source_offset=0, source_limit=5):
        if entry_id not in self.entries:
            raise CompanionError(ErrorCode.MISSING_DATA, "知识条目不存在")
        if offset < 0 or not 1 <= limit <= 12000 or source_offset < 0 or not 1 <= source_limit <= 20:
            raise CompanionError(ErrorCode.INVALID_INPUT, "读取范围超限")
        entry = self.entries[entry_id]
        body = self.package.bodies[entry["body_path"]]
        metadata = {k: v for k, v in entry.items() if k not in {"sources", "claims"}}
        return ToolResult(data={"entry": metadata, "content": body[offset:offset + limit],
                                "next_offset": offset + limit if offset + limit < len(body) else None,
                                "claims": entry.get("claims", [])[source_offset:source_offset+source_limit],
                                "next_source_offset": source_offset+source_limit if source_offset+source_limit < len(entry["sources"]) else None},
                          sources=entry["sources"][source_offset:source_offset+source_limit], versions={"knowledge": self.package.manifest["version"]})
