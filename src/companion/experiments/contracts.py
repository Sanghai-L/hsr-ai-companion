"""Content identity excludes only explicit top-level run metadata."""
from copy import deepcopy
import hashlib
import math
import unicodedata

from companion import __version__
from companion.contracts import CompanionError, ErrorCode, ToolResult, canonical
from companion.contracts.results import validator

RULES_VERSION = "p3-1"


def check(schema, value):
    errors = list(validator(schema).iter_errors(value))
    missing = []
    for error in errors:
        if error.validator == "required" and isinstance(error.instance, dict):
            prefix = ".".join(map(str, error.absolute_path))
            missing.extend((prefix + "." if prefix else "") + k for k in error.validator_value if k not in error.instance)
    if missing:
        raise CompanionError(ErrorCode.MISSING_DATA, "缺少计算条件", details={"fields": sorted(set(missing))})
    if errors:
        error = errors[0]
        raise CompanionError(ErrorCode.INVALID_INPUT, "计算输入不符合合同", details={
            "path": ".".join(map(str, error.absolute_path)), "reason": error.message[:350]})
    try:
        canonical(value)
    except (ValueError, TypeError, OverflowError):
        raise CompanionError(ErrorCode.INVALID_INPUT, "数值必须有限且可序列化")
    return value


def normalize(value):
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            key = unicodedata.normalize("NFC", key)
            if key in result:
                raise CompanionError(ErrorCode.INVALID_INPUT, "Unicode 规范化后出现重复字段")
            result[key] = normalize(item)
        return result
    if isinstance(value, list):
        return [normalize(item) for item in value]
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CompanionError(ErrorCode.INVALID_INPUT, "数值必须有限")
        return int(value) if value.is_integer() else value
    return value


def prepare(experiment):
    check("experiment.schema.json", experiment)
    value = normalize(deepcopy(experiment))
    if value["versions"]["rules"] != RULES_VERSION or value["versions"]["engine"] != __version__:
        raise CompanionError(ErrorCode.VERSION_INCOMPATIBLE, "执行代码／规则与实验指纹版本不一致",
                             details={"expected": {"engine": __version__, "rules": RULES_VERSION}})
    if value["conditions"]["investment"] == "real_account" and not value["conditions"].get("snapshot_id"):
        raise CompanionError(ErrorCode.MISSING_DATA, "真实账号实验需要快照", details={"fields": ["conditions.snapshot_id"]})
    return value


def fingerprint(experiment):
    value = prepare(experiment)
    value.pop("run", None)
    return hashlib.sha256(canonical(value)).hexdigest()


def comparison(left, right, *, declaration=None):
    left, right = prepare(left), prepare(right)
    differences = []
    for field in ("kind", "conditions", "versions", "budget", "source_refs", "assumptions"):
        if left[field] != right[field]:
            differences.append(field)
    if left["kind"] != right["kind"]:
        raise CompanionError(ErrorCode.VERSION_INCOMPATIBLE, "不同计算层级不可生成排名", details={"fields": differences})
    if differences and not declaration:
        raise CompanionError(ErrorCode.VERSION_INCOMPATIBLE, "比较口径不同，需要说明差异", details={"fields": differences})
    return {"left_fingerprint": fingerprint(left), "right_fingerprint": fingerprint(right),
            "differences": differences, "declaration": declaration,
            "ranking_permitted": not differences, "conditions": left["conditions"]}


def compare_request(request):
    check("comparison.schema.json", request)
    result = comparison(request["left"], request["right"], declaration=request.get("declaration"))
    return ToolResult(data=result, warnings=["已声明不同口径；仅供情景对照，不生成无条件排名"] if result["differences"] else [])
