"""Freeze source-aligned stage evidence without guessing schedules from period IDs."""
from datetime import datetime, timezone
import hashlib
import json
import re

from companion.contracts import CompanionError, ErrorCode, ToolResult, canonical

INDEX = {"memory_of_chaos": "maze", "pure_fiction": "maze_extra", "apocalyptic_shadow": "maze_boss"}


def stamp(value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo is not None else None
    except ValueError:
        return None


def check_current(cache, mode, *, offline=False, period_id=None, region=None, clock=None):
    now = (clock or (lambda: datetime.now(timezone.utc)))()
    fallback = {"mode": mode, "current_confirmed": False, "kind": "historical_or_generic",
                "region": region, "period_id": period_id, "checked_at": now.isoformat(),
                "representative_analysis_available": True, "parameters": None}
    if mode not in INDEX:
        return ToolResult(status="partial", data=fallback, missing_fields=["current_period_and_enemy_traits"],
                          warnings=["此模式尚无已核验的当前期数连接器；仅讨论带日期规则或通用代表性场景"])
    captures = []

    def read(url):
        result = cache.fetch(url, offline=offline, max_age=3600, force=False, limit=2*1024*1024)
        data = result.data
        content = data["content"]
        captures.append({"url": url, "observed_at": data["observed_at"],
                         "sha256": hashlib.sha256(content.encode()).hexdigest(), "fresh": result.status == "success"})
        return json.loads(content)

    try:
        manifest = read("https://static.nanoka.cc/manifest.json")
        live = manifest["hsr"]["live"]
        if not isinstance(live, str) or not re.fullmatch(r"\d+\.\d+", live):
            raise ValueError("invalid released marker")
        index = read(f"https://static.nanoka.cc/hsr/{live}/{INDEX[mode]}.json")
        if not isinstance(index, dict) or len(index) > 500:
            raise ValueError("stage index changed")
        active = []
        for key, row in index.items():
            if not isinstance(row, dict):
                raise ValueError("row changed")
            start, end = stamp(row.get("live_begin") or row.get("begin")), stamp(row.get("live_end") or row.get("end"))
            if start and end and start <= now < end:
                active.append(str(key))
        selected = str(period_id) if period_id is not None else (active[0] if len(active) == 1 else None)
        if selected is not None and (not re.fullmatch(r"\d{1,8}", selected) or selected not in index):
            raise CompanionError(ErrorCode.MISSING_DATA, "所选期数不在正式服来源索引中", details={"fields": ["period_id"]})
        row = index.get(selected) if selected else None
        current = bool(row and selected in active and region and row.get("region") == region and all(c["fresh"] for c in captures))
        parameters = {key: row[key] for key in ("id", "zh", "en", "param", "begin", "end", "live_begin", "live_end", "region") if key in row} if row else None
        frozen = {**fallback, "period_id": selected, "game_version": live, "source_live_marker": live,
                  "current_confirmed": current, "kind": "source_aligned" if current else "historical_or_generic",
                  "parameters": parameters, "captures": captures, "active_period_candidates": active,
                  "freeze_fingerprint": hashlib.sha256(canonical({"mode": mode, "region": region, "parameters": parameters, "captures": captures})).hexdigest()}
        warnings = ["来源live版本号不等于区服当前期数；不依据ID大小、抓取时间或空排期推断当前", "来源参数仅作资料，未经映射与明确假设不注入比较公式"]
        return ToolResult(status="success" if current else "partial", data=frozen,
                          sources=[{"type": "web", "ref": c["url"], "observed_at": c["observed_at"]} for c in captures],
                          missing_fields=[] if current else ["verified_region_schedule_and_period"], warnings=warnings)
    except CompanionError as error:
        if error.code not in {ErrorCode.MISSING_DATA, ErrorCode.NETWORK_FAILURE, ErrorCode.BUDGET_EXHAUSTED}:
            raise
        return ToolResult(status="partial", data={**fallback, "captures": captures, "source_error": error.to_dict()},
                          warnings=["当前来源不可用或证据不足，保留通用／历史分析；不猜测当前关卡"], missing_fields=["verified_current_stage"])
    except (ValueError, KeyError, TypeError, UnicodeError):
        return ToolResult(status="partial", data={**fallback, "captures": captures},
                          warnings=["来源格式变化；当前期数无法确认"], missing_fields=["verified_current_stage"])
