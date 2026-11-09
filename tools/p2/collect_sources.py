"""Read a bounded set of pinned public documents; never fetch a UID here."""
import hashlib
import json
from pathlib import Path
import urllib.request

from record import ROOT, now, write_json


def main():
    lock = json.loads((ROOT / "manifests/upstreams.lock.json").read_bytes())
    upstream = next(u for u in lock["upstreams"] if u["id"] == "starrailres")
    sha = upstream["commit"]
    targets = [(name, f"https://raw.githubusercontent.com/Mar-7th/StarRailRes/{sha}/index_new/cn/{name}")
               for name in ("character_skills.json", "characters.json", "paths.json", "elements.json")]
    targets.append(("enka-api.md", "https://raw.githubusercontent.com/EnkaNetwork/API-docs/b94bc40528941126590e0eefb0f03278e7a44ec8/api.md"))
    records = []
    folder = ROOT / ".local/evidence/D021/sources"
    folder.mkdir(parents=True, exist_ok=True)
    for name, url in targets:
        path = folder / name
        origin = path.with_suffix(path.suffix + ".origin.json")
        if origin.exists() and path.exists():
            records.append(json.loads(origin.read_bytes()))
            continue
        request = urllib.request.Request(url, headers={"User-Agent": "HSRCompanion-P2/0.1 public-source-verification"})
        with urllib.request.urlopen(request, timeout=25) as response:
            body = response.read(6 * 1024 * 1024 + 1)
            if len(body) > 6 * 1024 * 1024:
                raise ValueError("source too large")
        path.write_bytes(body)
        record = {"url": url, "observed_at": now(), "sha256": hashlib.sha256(body).hexdigest(),
                  "bytes": len(body), "private_path": str(path.relative_to(ROOT)), "commit": sha if name.endswith(".json") else "b94bc40528941126590e0eefb0f03278e7a44ec8", "http_status": 200}
        write_json(origin, record)
        records.append(record)
        print(name, len(body), flush=True)
    write_json(".local/evidence/D021/source-verification.json", {"sources": records})


if __name__ == "__main__":
    main()
