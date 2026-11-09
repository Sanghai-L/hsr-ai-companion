"""One serializable envelope for CLI, MCP and in-process services."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from functools import lru_cache
import json
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from companion.resources import resource_text


class ErrorCode(StrEnum):
    INVALID_INPUT = "INVALID_INPUT"
    MISSING_DATA = "MISSING_DATA"
    UNSUPPORTED = "UNSUPPORTED"
    NETWORK_FAILURE = "NETWORK_FAILURE"
    VERSION_INCOMPATIBLE = "VERSION_INCOMPATIBLE"
    CONFIRMATION_REQUIRED = "CONFIRMATION_REQUIRED"
    CONFLICT = "CONFLICT"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    INTERNAL_FAILURE = "INTERNAL_FAILURE"


class CompanionError(Exception):
    def __init__(self, code: ErrorCode, message: str, *, retryable=False, details=None):
        super().__init__(message)
        self.code, self.message, self.retryable = code, message, retryable
        self.details = details or {}

    def to_dict(self):
        return {"code": self.code.value, "message": self.message,
                "retryable": self.retryable, "details": self.details}


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


@lru_cache(maxsize=16)
def validator(schema_name: str):
    schema = json.loads(resource_text("schemas", schema_name))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def validate(schema_name: str, value: Any):
    errors = sorted(validator(schema_name).iter_errors(value), key=lambda e: str(list(e.path)))
    if errors:
        first = errors[0]
        raise CompanionError(ErrorCode.INVALID_INPUT, "数据不符合合同", details={
            "path": "/".join(map(str, first.path)), "reason": first.message[:400]})
    canonical(value)  # reject NaN/Infinity even for arbitrary metadata
    return value


@dataclass
class ToolResult:
    status: str = "success"
    data: Any = None
    sources: list = field(default_factory=list)
    versions: dict = field(default_factory=dict)
    assumptions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)
    error: dict | None = None

    @classmethod
    def failure(cls, error: CompanionError, **kwargs):
        return cls(status="error", error=error.to_dict(), **kwargs)

    def to_dict(self):
        return validate("tool-result.schema.json", asdict(self))

    @classmethod
    def from_dict(cls, value):
        return cls(**validate("tool-result.schema.json", value))

    @property
    def exit_code(self):
        if self.status == "success":
            return 0
        if self.status == "partial":
            return 3
        code = self.error["code"]
        if code in {ErrorCode.INVALID_INPUT, ErrorCode.CONFIRMATION_REQUIRED, ErrorCode.CONFLICT}:
            return 2
        if code in {ErrorCode.MISSING_DATA, ErrorCode.UNSUPPORTED, ErrorCode.VERSION_INCOMPATIBLE}:
            return 3
        return 4

