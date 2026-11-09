import json

import pytest

from companion.contracts import CompanionError, ErrorCode, ToolResult, canonical, validate


def test_round_trip_preserves_unknown_zero_and_false():
    value = ToolResult(data={"unknown": None, "zero": 0, "owned": False}).to_dict()
    assert ToolResult.from_dict(json.loads(canonical(value))).to_dict() == value
    assert value["data"]["unknown"] is None


@pytest.mark.parametrize("code", list(ErrorCode))
def test_failures_are_not_empty_successes(code):
    result = ToolResult.failure(CompanionError(code, "失败示例", retryable=True))
    assert result.to_dict()["error"]["retryable"] is True
    assert result.status == "error" and result.exit_code != 0


def test_inconsistent_envelope_rejected():
    value = ToolResult(data=[]).to_dict()
    value["status"] = "error"
    with pytest.raises(CompanionError):
        ToolResult.from_dict(value)
    value["extra"] = "not permitted"
    with pytest.raises(CompanionError):
        validate("tool-result.schema.json", value)
    with pytest.raises(ValueError):
        canonical({"number": float("nan")})

