"""Identity, provenance, quantities and version compatibility are distinct."""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
import re

from companion.contracts import CompanionError, ErrorCode


class InformationState(StrEnum):
    VERIFIED = "official_verified"
    DISPUTED = "official_disputed"
    BETA = "beta"
    LEAK = "leak"
    STALE = "stale"
    UNKNOWN = "unknown"


class Evidence(StrEnum):
    PRIMARY = "primary"
    REPRODUCED = "reproduced"
    COMMUNITY = "community"
    HYPOTHESIS = "hypothesis"
    UNKNOWN = "unknown"


class Coverage(StrEnum):
    VERIFIED = "verified"
    APPROXIMATE = "approximate"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"


def require(condition, message):
    if not condition:
        raise CompanionError(ErrorCode.INVALID_INPUT, message)


def timestamp(value: str):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(parsed.tzinfo is not None, "时间必须包含时区")
    return parsed


@dataclass(frozen=True)
class CharacterForm:
    character_id: str
    form_id: str
    name: str

    def __post_init__(self):
        require(bool(self.character_id and self.form_id and self.name), "实体与形态 ID 不可省略")

    @property
    def key(self):
        return (self.character_id, self.form_id)


@dataclass(frozen=True)
class Measurement:
    value: Decimal | None
    unit: str
    state: str = "known"
    precision: Decimal | None = None

    def __post_init__(self):
        require(self.unit in {"flat", "ratio", "percent", "percentage_point", "speed", "av", "toughness", "count"},
                "单位未知，不可计算")
        require(self.state in {"known", "unknown", "not_owned"}, "未知数值状态")
        require((self.value is not None) == (self.state == "known"), "未知／未持有不能填为数值 0")
        if self.value is not None:
            require(not isinstance(self.value, bool), "数值不能是布尔值")
            object.__setattr__(self, "value", Decimal(str(self.value)))
            require(self.value.is_finite(), "数值必须有限")
        if self.precision is not None:
            object.__setattr__(self, "precision", Decimal(str(self.precision)))
            require(self.precision.is_finite() and self.precision > 0, "精度必须为正数")

    def ratio(self):
        require(self.unit in {"ratio", "percent", "percentage_point"}, "不能把该单位转换为比例")
        if self.value is None:
            return None
        return self.value if self.unit == "ratio" else self.value / 100


@dataclass(frozen=True)
class Attribute:
    field_id: str
    quantity: Measurement
    basis: str
    source_type: str
    source_ref: str
    observed_at: str
    confirmed: bool

    def __post_init__(self):
        require(self.basis in {"base", "equipment_bonus", "public_panel"}, "属性来源层次未知")
        require(self.source_type in {"manual", "uid_public", "derived", "synthetic"}, "字段来源未知")
        require(bool(self.field_id and self.source_ref), "字段与来源引用不可缺失")
        timestamp(self.observed_at)


def combine_attributes(base: Attribute, bonus: Attribute):
    require(base.basis == "base" and bonus.basis == "equipment_bonus", "公开面板不可再次叠加装备")
    require(base.field_id == bonus.field_id and base.quantity.unit == bonus.quantity.unit, "字段或单位不一致")
    if base.quantity.value is None or bonus.quantity.value is None:
        return Measurement(None, base.quantity.unit, "unknown")
    return Measurement(base.quantity.value + bonus.quantity.value, base.quantity.unit)


@dataclass(frozen=True)
class VersionSet:
    game: str | None
    region: str | None
    period: str | None
    knowledge: str | None = None
    data_commit: str | None = None
    engine: str | None = None
    rules: str | None = None
    snapshot: str | None = None


def assert_compatible(left: VersionSet, right: VersionSet, *, fields=("game", "region", "period"),
                      allow_cross_version=False):
    missing = [name for name in fields if getattr(left, name) is None or getattr(right, name) is None]
    if missing:
        raise CompanionError(ErrorCode.MISSING_DATA, "版本资料未知", details={"fields": missing})
    different = [name for name in fields if getattr(left, name) != getattr(right, name)]
    if different and not allow_cross_version:
        raise CompanionError(ErrorCode.VERSION_INCOMPATIBLE, "对照条件版本不一致", details={"fields": different})
    return ["显式跨版本假设实验：" + ",".join(different)] if different else []


def version_tuple(value):
    require(isinstance(value, str) and re.fullmatch(r"\d+\.\d+\.\d+", value) is not None,
            "发布版本必须采用 x.y.z")
    return tuple(map(int, value.split(".")))

