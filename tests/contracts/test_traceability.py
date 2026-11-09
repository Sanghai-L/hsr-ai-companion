"""Historical stage evidence must not hide missing acceptance owners."""
import re
from pathlib import Path


def test_primary_acceptance_registry_is_unique_and_complete_with_historical_evidence():
    trace = (Path(__file__).resolve().parents[2]/"docs/requirements/traceability.md").read_text(encoding="utf-8")
    owner_table = trace.split("| 验收 | 需求 |",1)[1].split("\n\n",1)[0]
    owners = re.findall(r"^\| (A\d{2}) \|",owner_table,re.M)
    assert owners == [f"A{i:02}" for i in range(1,25)]
    assert len(re.findall(r"^\| (A\d{2}) \|",trace,re.M)) > 24
    assert all(re.search(rf"^\| {owner} \|.*D\d{{3}}",owner_table,re.M) for owner in owners)
