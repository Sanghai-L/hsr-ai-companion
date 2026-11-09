from decimal import Decimal

import pytest

from companion.contracts import CompanionError, validate
from companion.domain import Attribute, CharacterForm, Measurement, VersionSet, assert_compatible, combine_attributes


def test_forms_and_ownership_do_not_collapse():
    assert CharacterForm("march7", "preservation", "三月七").key != CharacterForm("march7", "hunt", "三月七").key
    zero = Measurement(0, "count")
    unknown = Measurement(None, "count", "unknown")
    absent = Measurement(None, "count", "not_owned")
    assert len({zero, unknown, absent}) == 3
    with pytest.raises(CompanionError):
        Measurement(0, "count", "unknown")


def test_units_precision_and_panel_double_count():
    assert Measurement(20, "percentage_point").ratio() == Decimal("0.2")
    assert Measurement(100, "speed").precision is None
    with pytest.raises(CompanionError):
        Measurement(4, "unknown_unit")
    def attr(value, basis):
        return Attribute("atk", Measurement(value, "flat"), basis, "synthetic", "fixture", "2026-11-06T12:00:00+08:00", True)
    assert combine_attributes(attr(100, "base"), attr(20, "equipment_bonus")).value == 120
    with pytest.raises(CompanionError, match="公开面板"):
        combine_attributes(attr(120, "public_panel"), attr(20, "equipment_bonus"))


def test_version_unknown_conflict_and_explicit_hypothesis():
    baseline = VersionSet("4.4.1", "cn", "1034")
    with pytest.raises(CompanionError) as error:
        assert_compatible(baseline, VersionSet(None, "cn", "1034"))
    assert error.value.code == "MISSING_DATA"
    newer = VersionSet("4.5.0", "cn", "1034")
    with pytest.raises(CompanionError):
        assert_compatible(baseline, newer)
    assert assert_compatible(baseline, newer, allow_cross_version=True)


def test_snapshot_schema_rejects_unitless_and_unknown_as_zero():
    snapshot = {"account_id": "a", "snapshot_id": "s", "observed_at": "2026-11-06T00:00:00Z",
                "versions": {"game": None}, "roster_completeness": "partial", "characters": [], "equipment": [],
                "fields": [{"entity_id": "account", "field_id": "jade", "quantity": {
                    "value": None, "unit": "count", "state": "unknown", "precision": None},
                    "source": {"type": "synthetic", "ref": "fixture", "observed_at": "2026-11-06T00:00:00Z"},
                    "confirmed": False, "basis": "record"}]}
    validate("account-snapshot.schema.json", snapshot)
    snapshot["fields"][0]["quantity"]["value"] = 0
    with pytest.raises(CompanionError):
        validate("account-snapshot.schema.json", snapshot)

