"""Local account configuration and manual data; reads never query providers."""
import json
import re
import uuid

from companion.contracts import CompanionError, ErrorCode, validate
from companion.storage.database import identifier, now

REGIONS = ["CN_OFFICIAL", "CN_CHANNEL", "ASIA", "AMERICA", "EUROPE", "TW_HK_MO"]
UNSET = object()


class AccountService:
    def __init__(self, store):
        self.store = store

    def configure(self, account_id, *, label=None, uid=UNSET, region=UNSET, style=UNSET, make_default=False):
        identifier(account_id)
        if label is not None and (not isinstance(label, str) or not 1 <= len(label) <= 100):
            raise CompanionError(ErrorCode.INVALID_INPUT, "账号名称为空或超限")
        if uid is not UNSET and uid is not None and (not isinstance(uid, str) or not re.fullmatch(r"\d{9,10}", uid)):
            raise CompanionError(ErrorCode.INVALID_INPUT, "UID 应为 9～10 位数字；此处仅本地记录")
        if region is not UNSET and region is not None and region not in REGIONS:
            raise CompanionError(ErrorCode.INVALID_INPUT, "区服标记不支持")
        if style is not UNSET and style not in {None, "A", "B"}:
            raise CompanionError(ErrorCode.INVALID_INPUT, "交流风格请选择 A 或 B")
        with self.store.transaction() as connection:
            row = connection.execute("SELECT * FROM accounts WHERE id=?", (account_id,)).fetchone()
            existing = dict(row) if row else {"id": account_id, "label": label or account_id,
                "uid": None, "region": None, "style": None, "created_at": now()}
            if row and any(value is not UNSET and existing[key] is not None and value != existing[key]
                           for key, value in (("uid", uid), ("region", region))):
                raise CompanionError(ErrorCode.CONFLICT, "已有账号 UID／区服不能静默换绑；请使用另一个账号 ID")
            if label is not None:
                existing["label"] = label
            for key, value in (("uid", uid), ("region", region), ("style", style)):
                if value is not UNSET:
                    existing[key] = value
            connection.execute("INSERT INTO accounts VALUES(:id,:label,:uid,:region,:style,:created_at) "
                               "ON CONFLICT(id) DO UPDATE SET label=excluded.label,uid=excluded.uid,region=excluded.region,style=excluded.style", existing)
            selected = connection.execute("SELECT value FROM settings WHERE key='default_account_id'").fetchone()
            if make_default or selected is None:
                connection.execute("INSERT OR REPLACE INTO settings VALUES('default_account_id',?)", (account_id,))
        return self.summary(account_id)

    def resolve(self, account_id=None):
        if account_id is not None:
            self.store.require_account(account_id)
            return account_id
        with self.store.connection() as connection:
            row = connection.execute("SELECT value FROM settings WHERE key='default_account_id'").fetchone()
        if row is None:
            raise CompanionError(ErrorCode.MISSING_DATA, "尚未选择默认账号")
        self.store.require_account(row["value"])
        return row["value"]

    def select(self, account_id):
        account_id = self.resolve(account_id)
        with self.store.transaction() as connection:
            connection.execute("INSERT OR REPLACE INTO settings VALUES('default_account_id',?)", (account_id,))
        return self.summary(account_id)

    def summary(self, account_id):
        account = self.store.require_account(account_id)
        return {"account": account, "uid_import": self.import_state(account_id, account), "uid_refreshed": False}

    def import_state(self, account_id, account=None):
        account = account or self.store.require_account(account_id)
        with self.store.connection() as connection:
            if connection.execute("PRAGMA user_version").fetchone()[0] >= 2:
                row = connection.execute("SELECT 1 FROM uid_queries WHERE account_id=? AND state='success' LIMIT 1", (account_id,)).fetchone()
                if row:
                    return "imported_public_partial"
        return "pending" if account["uid"] else "missing_uid"

    def get(self, account_id=None):
        account_id = self.resolve(account_id)
        account = self.store.require_account(account_id)
        snapshot = self.store.latest_snapshot(account_id)
        return {"account": account, "snapshot": snapshot,
                "uid_import": self.import_state(account_id, account), "uid_refreshed": False}

    def changes(self, account_id, query_id, *, offset=0, limit=20):
        self.store.require_account(account_id)
        with self.store.connection() as connection:
            row = connection.execute("SELECT payload FROM uid_queries WHERE id=? AND account_id=? AND state='success'", (query_id, account_id)).fetchone()
        if row is None:
            raise CompanionError(ErrorCode.MISSING_DATA, "账号没有此公开导入记录")
        payload = json.loads(row["payload"])
        entries = [{"kind": kind, "change": value} for kind, values in payload["diff"].items() for value in values]
        return {"account_id": account_id, "query_id": query_id, "items": entries[offset:offset+limit],
                "next_offset": offset+limit if offset+limit < len(entries) else None}

    def list(self):
        with self.store.connection() as connection:
            # Public status summaries do not return raw UIDs.
            return [dict(row) for row in connection.execute("SELECT id,label,region,style FROM accounts ORDER BY created_at,id")]

    def manual_update(self, account_id, fields, *, expected_snapshot_id=UNSET):
        account_id = self.resolve(account_id)
        old = self.store.latest_snapshot(account_id)
        current_id = old["snapshot_id"] if old else None
        if expected_snapshot_id is not UNSET and expected_snapshot_id != current_id:
            raise CompanionError(ErrorCode.CONFLICT, "手工修订基于旧快照；请重新读取账号")
        snapshot = old or {"account_id": account_id, "snapshot_id": "unset", "observed_at": now(), "versions": {"game": None},
            "roster_completeness": "unknown", "characters": [], "equipment": [], "fields": []}
        values = {(field["entity_id"], field["field_id"]): field for field in snapshot["fields"]}
        updates = set()
        for field in fields:
            validate("account-field.schema.json", field)
            if field["source"]["type"] not in {"manual", "synthetic"}:
                raise CompanionError(ErrorCode.INVALID_INPUT, "手工资料必须保留手工／合成来源")
            key = (field.get("entity_id"), field.get("field_id"))
            if key in updates:
                raise CompanionError(ErrorCode.INVALID_INPUT, "本次手工字段重复")
            updates.add(key)
            values[key] = field
        snapshot = {**snapshot, "snapshot_id": uuid.uuid4().hex, "observed_at": now(), "fields": list(values.values())}
        validate("account-snapshot.schema.json", snapshot)
        self.store.put_snapshot(snapshot, expected_snapshot_id=current_id)
        return {"account_id": account_id, "snapshot_id": snapshot["snapshot_id"], "field_count": len(snapshot["fields"]),
                "uid_refreshed": False}

