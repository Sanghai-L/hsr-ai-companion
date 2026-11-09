"""Read only the user-selected released MoC period, never beta or latest data."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import urllib.request
import uuid

from record import ROOT, now, write_json

OUT = ROOT / ".local/evidence/D038/current-1036-11"


def fetch(name, url):
    prior = OUT / (name + ".origin.json")
    if prior.exists():
        (OUT / (name + ".previous-" + uuid.uuid4().hex[:10] + ".origin.json")).write_bytes(prior.read_bytes())
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "HSRCompanion-P4/0.1"})
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read(8 * 1024 * 1024 + 1)
            if len(raw) > 8 * 1024 * 1024:
                raise ValueError("source exceeds explicit 8 MiB limit")
            value = json.loads(raw)
            record = {"name": name, "url": url, "observed_at": now(), "status": response.status,
                      "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
        (OUT / name).write_bytes(raw)
        write_json(OUT / (name + ".origin.json"), record)
        return record, value
    except Exception as error:
        record = {"name": name, "url": url, "observed_at": now(), "status": "unavailable",
                  "error_type": type(error).__name__, "message": str(error)[:600]}
        write_json(OUT / (name + ".origin.json"), record)
        return record, None


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    manifest_record, manifest = fetch("manifest.json", "https://static.nanoka.cc/manifest.json")
    # If live check is unavailable, the existing released snapshot is only a
    # candidate, and the report must not claim that it is current.
    live = manifest.get("hsr", {}).get("live") if manifest else None
    records = [manifest_record]
    if live:
        if not isinstance(live, str) or not live.replace(".", "").isdigit():
            raise ValueError("unknown live version format")
        urls = [("maze.json", f"https://static.nanoka.cc/hsr/{live}/maze.json"),
                ("period-1036.json", f"https://static.nanoka.cc/hsr/{live}/en/maze/1036.json"),
                ("monster.json", f"https://static.nanoka.cc/hsr/{live}/monster.json")]
        with ThreadPoolExecutor(max_workers=3) as pool:
            values = list(pool.map(lambda args: fetch(*args), urls))
        records.extend(record for record, _ in values)
    write_json(OUT / "collection.json", {"at": now(), "user_selected_period": "物竞天择", "period_id_candidate": "1036",
               "floor": 11, "sides": ["upper", "lower"], "region": None, "live_source_marker": live,
               "records": records, "game_ui_confirmed": False, "calibration_completed": False})
    print(json.dumps({"live_source_marker": live, "sources": [{"name": r["name"], "status": r["status"]} for r in records]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
