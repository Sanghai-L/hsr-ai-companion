"""D006: one documented public HSR example; cached and never auto-refreshed."""
import json
from pathlib import Path
import re
import urllib.error
import urllib.request

from common import ROOT, LOCAL, now, digest, write_json, update_task
from collect_sources import save


def main():
    update_task("D006", "IN_PROGRESS", summary="核对官方缓存政策与公开文档指定 HSR 样例；最多一次请求",
                next_step="实际字段、区服边界、去识别化合成故障样本", level="真实公开样例接口")
    origin = json.loads((LOCAL/"sources/enka-wrapper-tree.json").read_text(encoding="utf-8"))
    commit = origin["sha"]
    constants = save(f"https://raw.githubusercontent.com/seriaati/enka-py/{commit}/enka/constants/common.py",
                     Path("sources/enka-wrapper/enka/constants/common.py"))
    source = constants.read_text(encoding="utf-8")
    endpoint = re.search(r'^HSR_API_URL(?:\s*:\s*[^=]+)?\s*=\s*[\'"]([^\'\"]+)[\'\"]', source, re.M)
    if not endpoint:
        raise ValueError("Cannot establish HSR endpoint from pinned wrapper source")
    documentation = LOCAL / "sources/enka-wrapper/docs/profile.md"
    sample = re.search(r'enka\.HSRClient\(\).*?fetch_showcase\((\d+)\)', documentation.read_text(encoding="utf-8"), re.S)
    if not sample:
        raise ValueError("Missing documented HSR public example; will not invent a UID")
    url = endpoint.group(1).format(sample.group(1))
    if not url.startswith("https://enka.network/api/hsr/uid/"):
        raise ValueError("Unexpected service endpoint")
    evidence = LOCAL / "evidence/D006"
    raw_path = evidence / "public-example.raw.json"
    meta_path = evidence / "request.json"
    evidence.mkdir(parents=True, exist_ok=True)
    if not meta_path.exists():
        record = {"at": now(), "endpoint_template": endpoint.group(1), "request_url_private": url,
            "authorization": "P0 permits documented public samples; sample is explicitly used by the wrapper author's HSR docs and tests",
            "sample_document_url": f"https://github.com/seriaati/enka-py/blob/{commit}/docs/profile.md",
            "headers": {"User-Agent": "HSRCompanion-P0/0.1 (one-shot public documentation example; local research)"},
            "request_count": 1, "automatic_retry": False}
        # Persist intent before requesting: a failure must not trigger silent reruns.
        write_json(meta_path, record)
        req = urllib.request.Request(url, headers=record["headers"])
        try:
            with urllib.request.urlopen(req, timeout=35) as response:
                body = response.read(4*1024*1024+1)
                record.update(http_status=response.status,
                    response_headers={key: response.headers.get(key) for key in ("Content-Type", "Cache-Control", "Retry-After", "Date")})
            if len(body) > 4*1024*1024:
                raise ValueError("UID response exceeds probe budget")
            raw_path.write_bytes(body)
            record["raw_sha256"] = digest(raw_path)
        except urllib.error.HTTPError as exc:
            record.update(http_status=exc.code, error=str(exc), retry_after=exc.headers.get("Retry-After"))
        except Exception as exc:
            record["error"] = str(exc)
        write_json(meta_path, record)
    record = json.loads(meta_path.read_text(encoding="utf-8"))
    if record.get("http_status") != 200 or not raw_path.exists():
        update_task("D006", "BLOCKED", summary="公开样例查询未成功；不自动重试或换 UID",
                    blockers=[record.get("error", "No successful response")],
                    evidence=[".local/evidence/D006/request.json"], next_step="保留离线故障样本；等待服务可用")
        print(json.dumps({"http_status": record.get("http_status"), "success": False}))
        return
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    details = raw.get("detailInfo", {})
    avatars = details.get("avatarDetailList", [])
    summary = {"at": now(), "http_status": 200, "top_level_keys": sorted(raw),
        "detail_keys": sorted(details), "showcase_character_count": len(avatars),
        "avatar_keys": sorted({k for a in avatars for k in a}),
        "ttl": raw.get("ttl"), "region_verified": "Only the author's documented Asia public sample was tested",
        "full_roster_available": False, "backpack_available": False, "gacha_history_available": False,
        "available_resource_balance": False, "no_personal_player_data_in_shared_outputs": True}
    write_json(evidence/"field-observation.json", summary)
    print(json.dumps({"http_status":200, "showcase_count":len(avatars), "ttl":raw.get('ttl'),
                      "top_keys":summary['top_level_keys'], "avatar_keys":summary['avatar_keys']},ensure_ascii=False))


if __name__ == "__main__":
    main()
