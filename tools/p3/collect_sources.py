"""Bounded public source capture; originals remain in private evidence only."""
import hashlib
import json
import urllib.error
import urllib.request

from record import ROOT, now, write_json
from companion.calculators.gacha import OFFICIAL_PITY, OFFICIAL_LC, CURVE_SOURCE

SOURCES = [
    ("kqm-damage", "https://srl.keqingmains.com/combat-mechanics/damage/damage-formula", "community original theorycraft; page under construction; not official game specification"),
    ("kqm-speed", "https://hsr.keqingmains.com/misc/speed-guide/", "community original theorycraft"),
    ("kqm-speed-proof", "https://hsr.keqingmains.com/wp-content/uploads/2024/01/KQM_Bronya_Guide_SPD_Formula_Proofs.pdf", "community authored mathematical proof; first-page gauge relation"),
    ("official-warp-hard-rules", OFFICIAL_PITY, "official help updated 2025-09-23; actual banner details take precedence"),
    ("official-light-cone-guarantee", OFFICIAL_LC, "official help updated 2025-09-23; independent banner categories"),
    ("empirical-soft-pity-model", CURVE_SOURCE, "author-inferred curve, not official exact; light-cone onset disputed; featured-share theory not adopted"),
]


def main():
    records = []
    target = ROOT / ".local/evidence/D030/sources"
    target.mkdir(parents=True, exist_ok=True)
    for name, url, scope in SOURCES:
        filename = name + (".pdf" if url.endswith(".pdf") else ".html")
        cached = target / filename
        if cached.exists():
            data, status, capture = cached.read_bytes(), 200, "raw public response, previously captured this task"
        else:
            data, status, capture = None, None, None
        request = urllib.request.Request(url, headers={"User-Agent": "HSRCompanion-P3-validation/0.1"})
        if data is None:
            try:
                with urllib.request.urlopen(request, timeout=20) as response:
                    data = response.read(2000001)
                    if len(data) > 2000000:
                        raise RuntimeError("Source exceeds 2 MB validation limit")
                    status, capture = response.status, "raw public response"
                cached.write_bytes(data)
            except urllib.error.HTTPError as error:
                reviewed = ROOT / ".local/evidence/D030/web-reviewed" / (name + ".json")
                if error.code != 403 or not reviewed.exists():
                    raise
                data = reviewed.read_bytes()
                assert json.loads(data)["url"] == url
                status, capture = 403, "direct request blocked; actual web-tool page read, normalized factual extract hash only"
                cached = reviewed
        records.append({"id": name, "url": url, "observed_at": now(), "http_status": status,
                        "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data), "scope": scope, "capture": capture,
                        "private_capture": str(cached.relative_to(ROOT)).replace("\\", "/")})
        write_json(".local/evidence/D030/source-capture.json", records)
        print(name, status, len(data), flush=True)
    rulebook = ROOT / ".local/upstream/hsr-nous/repo/src/hsr_nous/sim_schema/rulebook.yaml"
    records.append({"id": "nous-rulebook-crosscheck", "url": "https://github.com/pzc2004/HSR_Nous/blob/f8935ddb407b297732fbd3c624d55897e3e648b9/src/hsr_nous/sim_schema/rulebook.yaml",
                    "observed_at": now(), "sha256": hashlib.sha256(rulebook.read_bytes()).hexdigest(),
                    "scope": "locked backend expression agreement for ordinary direct zones, not independent game accuracy"})
    write_json("benchmarks/formulas/sources.lock.json", {"schema_version": 1, "sources": records,
        "policy": "original summaries only; executable formulas shipped with program; knowledge sync cannot replace code"})


if __name__ == "__main__":
    main()
