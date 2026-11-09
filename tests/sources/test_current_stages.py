from datetime import datetime, timezone
import json

import pytest

from companion.contracts import CompanionError, ErrorCode, ToolResult
from companion.sources.current_stages import check_current

NOW = datetime(2026, 11, 8, 12, tzinfo=timezone.utc)


class Cache:
    def __init__(self, *, dates=False, stale=False, fail=False, live="4.6", malformed=False):
        self.calls = []
        self.dates, self.stale, self.fail, self.live, self.malformed = dates, stale, fail, live, malformed

    def fetch(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self.fail:
            raise CompanionError(ErrorCode.NETWORK_FAILURE, "synthetic source unavailable")
        value = {"hsr": {"live": self.live, "latest": "4.7.51"}} if url.endswith("manifest.json") else {
            "1036": {"id": "1036", "zh": "合成排期样本", "param": [.5], "region": "ASIA",
                     "live_begin": "2026-11-01T04:00:00+08:00" if self.dates else "",
                     "live_end": "2026-11-30T04:00:00+08:00" if self.dates else ""}}
        return ToolResult(status="partial" if self.stale else "success", data={"content": "[]" if self.malformed else json.dumps(value),
            "observed_at": "2026-11-08T11:59:00Z"})


@pytest.mark.parametrize("mode,path", [("memory_of_chaos", "maze"), ("pure_fiction", "maze_extra"), ("apocalyptic_shadow", "maze_boss")])
def test_live_marker_and_high_period_id_do_not_prove_current(mode, path):
    cache = Cache()
    result = check_current(cache, mode, period_id="1036", region="ASIA", clock=lambda: NOW)
    assert result.status == "partial" and not result.data["current_confirmed"]
    assert result.data["parameters"]["id"] == "1036" and result.data["freeze_fingerprint"]
    assert cache.calls[-1][0] == f"https://static.nanoka.cc/hsr/4.6/{path}.json"
    assert all("4.7" not in url and "latest" not in url for url, _ in cache.calls)


def test_explicit_region_and_aware_active_dates_are_required_to_confirm():
    result = check_current(Cache(dates=True), "memory_of_chaos", region="ASIA", clock=lambda: NOW)
    assert result.status == "success" and result.data["current_confirmed"]
    assert not check_current(Cache(dates=True), "memory_of_chaos", region="CN", clock=lambda: NOW).data["current_confirmed"]
    assert not check_current(Cache(dates=True, stale=True), "memory_of_chaos", region="ASIA", offline=True, clock=lambda: NOW).data["current_confirmed"]


@pytest.mark.parametrize("kwargs", [{"fail": True}, {"live": "4.7.51"}, {"malformed": True}])
def test_network_unknown_release_or_changed_format_degrades_without_fabricating(kwargs):
    result = check_current(Cache(**kwargs), "memory_of_chaos", region="ASIA", clock=lambda: NOW)
    assert result.status == "partial" and not result.data["current_confirmed"]
    assert result.data["representative_analysis_available"] and result.missing_fields


def test_aa_unknown_connector_is_explicit_and_never_guesses_endpoint():
    cache = Cache()
    result = check_current(cache, "anomaly_arbitration", clock=lambda: NOW)
    assert result.status == "partial" and not cache.calls
