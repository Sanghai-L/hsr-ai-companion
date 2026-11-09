"""Account-scoped SQLite transactions and immutable Markdown research."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import uuid

from companion.contracts import CompanionError, ErrorCode, canonical, validate
from companion.resources import resource_text
from .paths import SafeRoot, file_lock

ANY_SNAPSHOT = object()


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}", value):
        raise CompanionError(ErrorCode.INVALID_INPUT, "本地 ID 格式错误")
    return value


class Store:
    def __init__(self, directory, *, read_only=False):
        self.read_only = read_only
        if read_only and not Path(directory).is_dir():
            raise CompanionError(ErrorCode.MISSING_DATA, "尚无本地账号数据库")
        self.files = SafeRoot(directory)
        if read_only:
            if not self.files.path("personal.sqlite3").is_file():
                raise CompanionError(ErrorCode.MISSING_DATA, "尚无本地账号数据库")
            with self.connection() as connection:
                if connection.execute("PRAGMA user_version").fetchone()[0] not in {1, 2}:
                    raise CompanionError(ErrorCode.VERSION_INCOMPATIBLE, "个人数据库版本不兼容")
            return
        with file_lock(self.files, "migration.lock"):
            with self.connection() as connection:
                version = connection.execute("PRAGMA user_version").fetchone()[0]
                if version == 0:
                    connection.executescript(resource_text("migrations", "0001_initial.sql"))
                    version = 1
                if version == 1:
                    connection.executescript(resource_text("migrations", "0002_research.sql"))
                elif version != 2:
                    raise CompanionError(ErrorCode.VERSION_INCOMPATIBLE, "个人数据库版本不兼容")

    @contextmanager
    def connection(self):
        path = self.files.path("personal.sqlite3")
        for suffix in ("-journal", "-wal", "-shm"):
            self.files.path("personal.sqlite3" + suffix)
        connection = (sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=10, isolation_level=None)
                      if self.read_only else sqlite3.connect(path, timeout=10, isolation_level=None))
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=10000")
        connection.execute("PRAGMA synchronous=FULL")
        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def transaction(self):
        if self.read_only:
            raise CompanionError(ErrorCode.UNSUPPORTED, "只读存储不允许写事务")
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                yield connection
                connection.commit()
            except BaseException:
                connection.rollback()
                raise

    def require_account(self, account_id, connection=None):
        identifier(account_id)
        if connection is None:
            with self.connection() as connection:
                return self.require_account(account_id, connection)
        row = connection.execute("SELECT * FROM accounts WHERE id=?", (account_id,)).fetchone()
        if row is None:
            raise CompanionError(ErrorCode.MISSING_DATA, "本地账号不存在")
        return dict(row)

    def put_snapshot(self, value, *, expected_snapshot_id=ANY_SNAPSHOT, transaction_hook=None):
        validate("account-snapshot.schema.json", value)
        keys = [(c["character_id"], c["form_id"]) for c in value["characters"]]
        instances = [c["instance_id"] for c in value["equipment"]]
        if len(set(keys)) != len(keys) or len(set(instances)) != len(instances):
            raise CompanionError(ErrorCode.INVALID_INPUT, "重复的角色形态或装备实例")
        content = canonical(value)
        with self.transaction() as connection:
            self.require_account(value["account_id"], connection)
            if expected_snapshot_id is not ANY_SNAPSHOT:
                latest = connection.execute("SELECT id FROM snapshots WHERE account_id=? ORDER BY observed_at DESC,rowid DESC LIMIT 1",
                                            (value["account_id"],)).fetchone()
                if (latest["id"] if latest else None) != expected_snapshot_id:
                    raise CompanionError(ErrorCode.CONFLICT, "账号快照已变化，请读取差异后重试")
            existing = connection.execute("SELECT sha256 FROM snapshots WHERE id=?", (value["snapshot_id"],)).fetchone()
            sha = hashlib.sha256(content).hexdigest()
            if existing:
                if existing["sha256"] != sha:
                    raise CompanionError(ErrorCode.CONFLICT, "快照不可变；请创建新 ID")
                return value["snapshot_id"]
            connection.execute("INSERT INTO snapshots VALUES(?,?,?,?,?)", (
                value["snapshot_id"], value["account_id"], content.decode(), sha, value["observed_at"]))
            for field in value["fields"]:
                connection.execute("INSERT INTO field_sources VALUES(?,?,?,?,?)", (
                    value["account_id"], value["snapshot_id"], field["entity_id"], field["field_id"], canonical(field).decode()))
            if transaction_hook:
                transaction_hook(connection)
        return value["snapshot_id"]

    def latest_snapshot(self, account_id):
        self.require_account(account_id)
        with self.connection() as connection:
            row = connection.execute("SELECT payload FROM snapshots WHERE account_id=? ORDER BY observed_at DESC, rowid DESC LIMIT 1",
                                     (account_id,)).fetchone()
        return json.loads(row["payload"]) if row else None

    def append_operation(self, kind, payload, account_id=None):
        with self.transaction() as connection:
            if account_id is not None:
                self.require_account(account_id, connection)
            connection.execute("INSERT INTO operations VALUES(?,?,?,?,?)", (
                uuid.uuid4().hex, account_id, kind, canonical(payload).decode(), now()))

    def create_research(self, account_id, title, body, *, metadata=None, after_file=None):
        self.require_account(account_id)
        if not isinstance(title, str) or not title or len(title) > 512 or not isinstance(body, str) or not body or len(body.encode()) > 131072:
            raise CompanionError(ErrorCode.INVALID_INPUT, "研究标题／正文为空或超限")
        record = {"id": uuid.uuid4().hex, "account_id": account_id, "title": title,
                  "created_at": now(), "details": metadata or {}}
        relative = f"research/{account_id}/{record['id']}.md"
        content = b"<!-- companion-research-v1\n" + canonical(record) + b"\n-->\n\n" + body.encode("utf-8")
        with file_lock(self.files, "research.lock"):
            self.files.write(relative, content, exclusive=True)
            if after_file:
                after_file()  # explicit crash injection for real process recovery tests
            self._index_research(record, relative, content)
        return record["id"]

    def _index_research(self, record, relative, content):
        with self.transaction() as connection:
            self.require_account(record["account_id"], connection)
            connection.execute("INSERT INTO research VALUES(?,?,?,?,?,?,?)", (
                record["id"], record["account_id"], record["title"], relative,
                hashlib.sha256(content).hexdigest(), canonical(record["details"]).decode(), record["created_at"]))
            if record["details"].get("memory_schema") == 1 and not record["details"].get("revision_of"):
                connection.execute("INSERT INTO memory_heads VALUES(?,?,?,1)", (record["account_id"], record["id"], record["id"]))

    def read_research(self, account_id, research_id):
        identifier(research_id)
        self.require_account(account_id)
        with self.connection() as connection:
            row = connection.execute("SELECT * FROM research WHERE account_id=? AND id=?", (account_id, research_id)).fetchone()
        if row is None:
            raise CompanionError(ErrorCode.MISSING_DATA, "该账号没有此研究")
        content = self.files.path(row["body_path"]).read_bytes()
        if hashlib.sha256(content).hexdigest() != row["sha256"]:
            raise CompanionError(ErrorCode.CONFLICT, "研究文件与索引不一致")
        return content.decode("utf-8").split("\n-->\n\n", 1)[1]

    def recover_research(self):
        report = {"recovered": [], "damaged": [], "missing": []}
        with file_lock(self.files, "research.lock"):
            with self.connection() as connection:
                rows = {r["body_path"]: dict(r) for r in connection.execute("SELECT * FROM research")}
            directory = self.files.mkdir("research")
            for candidate in directory.glob("*/*.md"):
                relative = candidate.relative_to(self.files.root).as_posix()
                try:
                    content = self.files.path(relative).read_bytes()
                    if len(content) > 140000 or not content.startswith(b"<!-- companion-research-v1\n"):
                        raise ValueError("bad envelope")
                    encoded = content.split(b"\n", 1)[1].split(b"\n-->\n\n", 1)[0]
                    record = json.loads(encoded)
                    identifier(record["id"])
                    identifier(record["account_id"])
                    if relative != f"research/{record['account_id']}/{record['id']}.md":
                        raise ValueError("identity mismatch")
                    if relative in rows:
                        if hashlib.sha256(content).hexdigest() != rows[relative]["sha256"]:
                            raise ValueError("hash mismatch")
                    else:
                        self._index_research(record, relative, content)
                        report["recovered"].append(record["id"])
                except (ValueError, KeyError, CompanionError, OSError, sqlite3.Error):
                    report["damaged"].append(relative)
            for relative in rows:
                if not self.files.path(relative).exists():
                    report["missing"].append(relative)
        return report

