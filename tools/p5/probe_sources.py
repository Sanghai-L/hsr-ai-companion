"""Small explicit public-source probe; results never assert current without schedule."""
from datetime import datetime, timezone
import json
from pathlib import Path
import uuid

from companion.sources.cache import SourceCache
from companion.sources.current_stages import check_current

ROOT = Path(__file__).resolve().parents[2]


def main():
    path = ROOT / ".local/evidence/D048" / ("sources-" + uuid.uuid4().hex[:10])
    path.mkdir(parents=True)
    cache = SourceCache(path/"cache")
    results = {}
    for mode, period in [("memory_of_chaos", "1036"), ("pure_fiction", None), ("apocalyptic_shadow", None), ("anomaly_arbitration", None)]:
        results[mode] = check_current(cache, mode, period_id=period, region="ASIA").to_dict()
    (path/"results.json").write_text(json.dumps({"at": datetime.now(timezone.utc).isoformat(), "results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"evidence": str(path), "results": {mode: {"status": result["status"], "current_confirmed": result["data"]["current_confirmed"],
          "source_live_marker": result["data"].get("source_live_marker"), "captures": len(result["data"].get("captures", [])),
          "source_error": result["data"].get("source_error")} for mode, result in results.items()}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
