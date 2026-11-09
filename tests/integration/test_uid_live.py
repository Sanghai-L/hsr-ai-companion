"""Explicit, one-request public sample validation; raw identity stays in .local."""
import json
import os
from pathlib import Path
import uuid

import pytest

from companion.accounts import AccountService
from companion.accounts.refresh import AccountRefresh
from companion.storage import Store

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.live
def test_authorized_public_uid_import_once():
    path = os.environ.get("HSR_TEST_UID_INPUT")
    assert path, "set HSR_TEST_UID_INPUT to a private explicitly authorized input file"
    request = json.loads(Path(path).read_bytes())
    assert request.get("authorization") and request.get("uid") and request.get("region")
    directory = ROOT / ".local/probes/p2/uid-live" / uuid.uuid4().hex
    store = Store(directory)
    AccountService(store).configure("public-example", uid=request["uid"], region=request["region"], style="B")
    result = AccountRefresh(store).refresh("public-example", "live-request:" + str(Path(path).absolute()), "import")
    assert result.status == "success" and result.data["uid_refreshed"]
    snapshot = store.latest_snapshot("public-example")
    raw = json.loads(store.files.path(f"uid/public-example/{result.data['query_id']}.json").read_bytes())
    body = json.loads(raw["raw_utf8"])
    assert len(body["detailInfo"].get("avatarDetailList", [])) == result.data["showcase_count"]
    for avatar in body["detailInfo"].get("avatarDetailList", []):
        cid = str(avatar["avatarId"])
        form = f"{cid}:{avatar.get('enhancedId') or 'base'}"
        for name in ("level", "rank", "promotion"):
            field = next(f for f in snapshot["fields"] if f["entity_id"] == "character:" + form and f["field_id"] == name)
            assert field["quantity"]["value"] == avatar.get(name)
    evidence = {"data_dir": str(directory), "result": result.to_dict(), "authorization": request["authorization"],
                "actual_request_count": 1, "field_correspondence_checked": ["avatarId", "enhancedId", "level", "promotion", "rank"],
                "layer": "real public API; documented public example, not user private account"}
    output = ROOT / ".local/evidence/D024/uid-live.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
