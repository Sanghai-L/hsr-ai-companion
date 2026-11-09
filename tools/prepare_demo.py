"""Prepare a new synthetic-only demo directory; refuse existing data."""
import argparse
from pathlib import Path
import uuid

from companion.accounts import AccountService
from companion.storage import SafeRoot, Store
from companion.storage.database import now


def prepare(directory):
    path = Path(directory)
    if path.exists() and any(path.iterdir()):
        raise ValueError("演示目录必须为空或不存在；不会覆盖已有玩家数据")
    files = SafeRoot(path)
    files.write("SYNTHETIC-DEMO.txt", b"Synthetic local demo; not a real UID account.\n", exclusive=True)
    accounts = AccountService(Store(files.mkdir("personal")))
    for key, style, amount in (("demo-a", "A", 1600), ("demo-b", "B", 0)):
        accounts.configure(key, label="合成演示 " + key, style=style)
        accounts.manual_update(key, [{"entity_id": "account", "field_id": "stellar_jade",
            "quantity": {"value": amount, "unit": "count", "state": "known", "precision": None},
            "source": {"type": "synthetic", "ref": "prepare_demo original synthetic fixture", "observed_at": now()},
            "confirmed": True, "basis": "record"}])
    accounts.select("demo-a")
    return {"synthetic": True, "data_dir": str(files.root), "accounts": ["demo-a", "demo-b"]}


if __name__ == "__main__":
    import json
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.data_dir), ensure_ascii=False))
