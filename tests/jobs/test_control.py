from companion.simulation.compare import compare
from tests.simulation.representative_cases import case


def test_budget_shared_across_candidates_never_ranks_partial_results():
    value = case()
    value["budget"]["max_actions"] = 8
    result = compare(value)
    assert result.status == "partial" and result.data["termination"] == "actions_budget"
    assert result.data["ranking"] is None
    assert result.data["outcomes"][0]["status"] == "completed"


def test_time_exhaustion_before_start_is_not_success():
    values = iter([0, 2])
    request = case()
    request["budget"]["max_seconds"] = 1
    result = compare(request, clock=lambda: next(values))
    assert result.status == "partial" and result.data["termination"] == "time_budget"
    assert len(result.data["uncomputed_candidates"]) == 2


def test_cooperative_cancellation_starts_no_windows_worker(monkeypatch):
    import subprocess
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("unexpected worker")))
    calls = []
    def cancelled():
        calls.append(1)
        return len(calls) > 6
    result = compare(case(), cancelled=cancelled)
    assert result.status == "partial" and result.data["termination"] == "cancelled"
    assert result.data["ranking"] is None and len(calls) < 12


def test_candidate_budget_is_an_explicit_partial_result():
    request = case()
    request["budget"]["max_candidates"] = 1
    result = compare(request)
    assert result.data["termination"] == "candidates_budget" and result.data["uncomputed_candidates"] == ["herta"]
