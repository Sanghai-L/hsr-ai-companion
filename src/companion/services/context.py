"""Explicit per-install context. Construction and doctor do not initialize accounts."""
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3

from companion.contracts import CompanionError, ErrorCode
from companion.storage import SafeRoot, Store
from companion.updates.knowledge import KnowledgeSync
from companion.updates.program import ProgramUpdates
from companion.updates.source import ReleaseSource


class Context:
    def __init__(self, data_dir, *, offline=False):
        self.data_dir = Path(os.path.abspath(data_dir))
        self.offline = offline

    @property
    def store(self):
        files = SafeRoot(self.data_dir)
        return Store(files.mkdir("personal"))

    @property
    def read_store(self):
        if not self.data_dir.is_dir():
            raise CompanionError(ErrorCode.MISSING_DATA, "尚无本地账号数据库")
        files = SafeRoot(self.data_dir)
        return Store(files.path("personal"), read_only=True)

    @property
    def config(self):
        if not self.data_dir.exists():
            return {}
        files = SafeRoot(self.data_dir)
        path = files.path("config.json")
        if not path.exists():
            return {}
        if path.stat().st_size > 65536:
            raise CompanionError(ErrorCode.INVALID_INPUT, "本机发布源配置超限")
        try:
            value = json.loads(path.read_bytes())
        except ValueError as error:
            raise CompanionError(ErrorCode.INVALID_INPUT, "本机发布源配置损坏") from error
        if not isinstance(value, dict) or set(value) - {"knowledge_source", "program_source", "check_interval"}:
            raise CompanionError(ErrorCode.INVALID_INPUT, "本机发布源配置包含未知字段")
        if any(not isinstance(value[key], str) or not value[key] for key in ("knowledge_source", "program_source") if key in value):
            raise CompanionError(ErrorCode.INVALID_INPUT, "发布源必须为非空字符串")
        if type(value.get("check_interval", 21600)) is not int or not 60 <= value.get("check_interval", 21600) <= 604800:
            raise CompanionError(ErrorCode.INVALID_INPUT, "发布检查间隔须为 60～604800 秒")
        return value

    def knowledge(self):
        config = self.config
        files = SafeRoot(self.data_dir)
        location = config.get("knowledge_source")
        return KnowledgeSync(files.mkdir("knowledge"), source=self.release_source(location) if location else None,
                             interval=config.get("check_interval", 21600))

    def program(self):
        import sys
        config = self.config
        location = config.get("program_source")
        scope = Path(os.environ.get("HSR_COMPANION_INSTALL_ROOT", sys.prefix))
        return ProgramUpdates(self.store, scope, source=self.release_source(location) if location else None,
                              interval=config.get("check_interval", 21600))

    def release_source(self, location):
        from companion.release.signing import load_trust
        path = SafeRoot(self.data_dir).path("release-trust.json")
        keys = load_trust(path) if path.is_file() else []
        return ReleaseSource(location, trusted_keys=keys, require_signature=True, audit=self.network_audit)

    def network_audit(self, event):
        from companion.diagnostics.redaction import NetworkAudit
        NetworkAudit(SafeRoot(self.data_dir).mkdir("diagnostics")).record(event)

    def http(self, url, **kwargs):
        from companion.sources.http import fetch
        return fetch(url, audit=self.network_audit, **kwargs)

    def search(self):
        from companion.knowledge.package import KnowledgePackage
        from companion.knowledge.index import ensure_index
        from companion.knowledge.search import KnowledgeSearch
        from companion.resources import resource_text
        sync = self.knowledge()
        package = sync.current()
        if package is None:
            package = KnowledgePackage.decode(resource_text("knowledge", "bundle.json").encode("utf-8"))
            relative = f"bundled-{package.fingerprint}.index.json"
        else:
            relative = f"packages/{package.fingerprint}/search-index.json"
        return KnowledgeSearch(package, index=ensure_index(package, sync.files, relative))

    def sources(self):
        from companion.sources.cache import SourceCache
        return SourceCache(SafeRoot(self.data_dir).mkdir("sources"), transport=self.http)

    def inspect(self):
        result = {"initialized": False, "account_count": 0, "default_account_id": None,
                  "style": None, "uid_import": "pending", "pending_conflicts": 0}
        if not self.data_dir.exists():
            return result
        files = SafeRoot(self.data_dir)
        personal_path = files.path("personal")
        if not personal_path.exists():
            return result
        personal = SafeRoot(personal_path)
        database = personal.path("personal.sqlite3")
        if not database.exists():
            return result
        for suffix in ("-journal", "-wal", "-shm"):
            personal.path("personal.sqlite3" + suffix)
        with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as connection:
            if connection.execute("PRAGMA user_version").fetchone()[0] not in {1, 2}:
                raise CompanionError(ErrorCode.VERSION_INCOMPATIBLE, "个人数据库版本不兼容")
            result["account_count"] = connection.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
            row = connection.execute("SELECT value FROM settings WHERE key='default_account_id'").fetchone()
            if row:
                selected = connection.execute("SELECT id,style,uid,region FROM accounts WHERE id=?", (row[0],)).fetchone()
                if selected:
                    result.update(default_account_id=selected[0], style=selected[1],
                                  initialized=bool(selected[1] and selected[2] and selected[3]),
                                  pending_conflicts=connection.execute("SELECT COUNT(*) FROM conflicts WHERE account_id=? AND state='pending'", (selected[0],)).fetchone()[0])
                    if connection.execute("PRAGMA user_version").fetchone()[0] >= 2:
                        imported = connection.execute("SELECT 1 FROM uid_queries WHERE account_id=? AND state='success' LIMIT 1", (selected[0],)).fetchone()
                        result["uid_import"] = "imported_public_partial" if imported else "pending" if selected[2] else "missing_uid"
        return result

