from copy import deepcopy
import math

import pytest

from companion.contracts import CompanionError
from companion.experiments import comparison, fingerprint
from companion.experiments.contracts import prepare
from companion.experiments.service import execute
from tests.experiments.helpers import fixture


def test_equivalent_numbers_key_order_unicode_and_run_metadata_have_same_fingerprint():
    left = fixture("damage")
    right = deepcopy(left)
    right["parameters"]["stat"]["value"] = 1000.0
    right["parameters"]["flat_damage"] = -0.0
    right["run"] = {"task_id": "different", "started_at": "2026-11-09T12:00:00Z"}
    assert fingerprint(left) == fingerprint(right)
    left["conditions"]["notes"] = "caf\u00e9"
    right["conditions"]["notes"] = "cafe\u0301"
    assert fingerprint(left) == fingerprint(right)


@pytest.mark.parametrize("field", ["parameters", "conditions", "versions", "budget", "source_refs", "assumptions"])
def test_semantic_changes_alter_fingerprint(field):
    left, right = fixture("damage"), fixture("damage")
    if field == "parameters":
        right[field]["multiplier"] = 3
    elif field == "conditions":
        right[field]["game_version"] = "4.7"
    elif field == "versions":
        right[field]["data"] = "new-data"
    elif field == "budget":
        right[field]["max_events"] = 2
    else:
        right[field].append("changed")
    assert fingerprint(left) != fingerprint(right)


def test_future_income_dates_remain_semantic_not_accidentally_removed():
    left, right = fixture("pull-plan"), fixture("pull-plan")
    right["parameters"]["income"][0]["available_on"] = "2026-11-10"
    assert fingerprint(left) != fingerprint(right)


def test_missing_fields_and_real_account_snapshot_are_specific():
    value = fixture("damage")
    del value["versions"]["data"]
    with pytest.raises(CompanionError) as exc:
        prepare(value)
    assert exc.value.code == "MISSING_DATA" and exc.value.details["fields"] == ["versions.data"]
    value = fixture("damage")
    value["conditions"]["investment"] = "real_account"
    with pytest.raises(CompanionError, match="快照"):
        prepare(value)


def test_comparisons_cannot_silently_rank_different_versions_or_investments():
    left, right = fixture("damage"), fixture("damage")
    right["conditions"]["investment"] = "ideal_upper_bound"
    with pytest.raises(CompanionError) as exc:
        comparison(left, right)
    assert exc.value.code == "VERSION_INCOMPATIBLE"
    assert comparison(left, right, declaration="玩家显式比较现实条件和理想上限")["ranking_permitted"] is False
    assert comparison(left, left)["ranking_permitted"] is True


def test_wrong_engine_rules_nan_and_unsupported_simulation_are_rejected():
    for field in ("engine", "rules"):
        value = fixture("damage")
        value["versions"][field] = "uninstalled"
        with pytest.raises(CompanionError) as exc:
            prepare(value)
        assert exc.value.code == "VERSION_INCOMPATIBLE"
    value = fixture("damage")
    value["parameters"]["flat_damage"] = math.nan
    with pytest.raises(CompanionError):
        fingerprint(value)
    value = fixture("damage")
    value["kind"] = "simulation"
    with pytest.raises(CompanionError) as exc:
        execute(value)
    assert exc.value.code == "UNSUPPORTED"
