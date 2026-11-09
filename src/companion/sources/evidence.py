"""Evidence is scoped to an account; reposts retain their upstream dependency."""
import hashlib
import json
import uuid

from companion.contracts import CompanionError, ErrorCode, ToolResult, canonical, validate
from companion.storage.database import now
from .http import public_url


class EvidenceService:
    def __init__(self, store):
        self.store = store

    def get(self, account_id, evidence_id, connection=None):
        if connection is None:
            with self.store.connection() as connection:
                return self.get(account_id, evidence_id, connection)
        row = connection.execute("SELECT payload FROM evidence WHERE id=? AND account_id=?", (evidence_id, account_id)).fetchone()
        if row is None:
            raise CompanionError(ErrorCode.MISSING_DATA, "此账号没有该证据")
        return json.loads(row["payload"])

    def register(self, account_id, claim, url, content, *, kind="host_search", applicable_version=None,
                 stance="uncertain", depends_on=None, origin_urls=None, observed_at=None, source_ref=None):
        self.store.require_account(account_id)
        if not claim.strip() or len(claim) > 500 or not content.strip() or len(content) > 30000:
            raise CompanionError(ErrorCode.INVALID_INPUT, "证据论点或内容为空／超限")
        if kind not in {"host_search", "host_page", "connector_page", "manual"} or stance not in {"supports", "opposes", "uncertain"}:
            raise CompanionError(ErrorCode.INVALID_INPUT, "证据类型或立场无效")
        url = public_url(url)
        dependencies = depends_on or []
        if len(dependencies) > 30 or len(origin_urls or []) > 30:
            raise CompanionError(ErrorCode.INVALID_INPUT, "来源依赖超限")
        roots = set(public_url(x) for x in origin_urls or [])
        with self.store.transaction() as connection:
            for dependency in dependencies:
                roots.update(self.get(account_id, dependency, connection)["root_sources"])
            if not roots:
                roots.add(url)
            evidence = {"id": uuid.uuid4().hex, "account_id": account_id, "claim": claim.strip(), "url": url,
                        "observed_at": observed_at or now(), "applicable_version": applicable_version,
                        "kind": kind, "verification": "search_summary" if kind == "host_search" else "reported_page" if kind == "host_page" else "fetched_page" if kind == "connector_page" else "manual_statement",
                        "content_sha256": hashlib.sha256(content.encode()).hexdigest(), "content": content,
                        "stance": stance, "depends_on": dependencies, "root_sources": sorted(roots),
                        "source_ref": source_ref, "trust": "data_only"}
            if len(canonical({k: v for k, v in evidence.items() if k != "content"})) > 12000:
                raise CompanionError(ErrorCode.INVALID_INPUT, "证据来源依赖元信息超限")
            validate("evidence.schema.json", evidence)
            connection.execute("INSERT INTO evidence VALUES(?,?,?,?,?)", (evidence["id"], account_id, evidence["claim"], canonical(evidence).decode(), now()))
        result = self.resolve(account_id, claim)
        result.data["registered_id"] = evidence["id"]
        return result

    def resolve(self, account_id, claim, *, limit=10, offset=0):
        self.store.require_account(account_id)
        with self.store.connection() as connection:
            rows = connection.execute("SELECT payload FROM evidence WHERE account_id=? AND claim=? ORDER BY created_at,id", (account_id, claim.strip())).fetchall()
        evidence = [json.loads(r["payload"]) for r in rows]
        independent = set()
        stances = set()
        for item in evidence:
            stances.add(item["stance"])
            independent.update(item["root_sources"])
        # Connected dependency sets form one provenance group, even with partially shared sources.
        groups = []
        for item in evidence:
            roots = set(item["root_sources"])
            overlap = [g for g in groups if g & roots]
            for group in overlap:
                roots |= group
                groups.remove(group)
            groups.append(roots)
        page = evidence[offset:offset+limit]
        def view(items):
            summaries = [{k: v for k, v in item.items() if k != "content"} | {"excerpt": item["content"][:800]} for item in items]
            sources = [{"type": "web", "ref": item["url"], "observed_at": item["observed_at"]} for item in items]
            return summaries, sources
        summaries, sources = view(page)
        while len(canonical([summaries, sources])) > 40000 and len(page) > 1:
            page.pop()
            summaries, sources = view(page)
        # Group fingerprints keep large provenance sets bounded; each paged item retains the actual URLs.
        group_fingerprints = [hashlib.sha256(canonical(sorted(g))).hexdigest() for g in groups]
        return ToolResult(data={"claim": claim, "items": summaries, "conflicting": {"supports", "opposes"} <= stances,
                                "provenance_groups": group_fingerprints[offset:offset+limit], "independent_group_count": len(groups),
                                "total": len(evidence), "next_offset": offset+len(page) if offset+len(page) < len(evidence) else None},
                          sources=sources,
                          warnings=["宿主搜索摘要只证明发现了资料；host_page 为宿主提供正文，独立性依赖已登记的转载链"])
