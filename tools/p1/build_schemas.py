"""Generate the reviewable, self-contained JSON Schema contracts."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def obj(properties, required=None, **extra):
    return {"type": "object", "properties": properties,
            "required": list(properties) if required is None else required,
            "additionalProperties": False, **extra}


def array(items, **kwargs):
    return {"type": "array", "items": items, **kwargs}


TEXT = {"type": "string", "minLength": 1, "maxLength": 8192}
ID = {"type": "string", "pattern": "^[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}$"}
SHA = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
TIME = {"type": "string", "format": "date-time"}
STRINGS = array(TEXT, maxItems=200)
NULLABLE_TEXT = {"anyOf": [TEXT, {"type": "null"}]}
VERSIONS = obj({name: NULLABLE_TEXT for name in (
    "game", "region", "period", "knowledge", "data_commit", "engine", "rules", "snapshot")}, [])
SOURCE = obj({"type": {"enum": ["manual", "uid_public", "derived", "synthetic", "maintainer", "web"]},
              "ref": TEXT, "observed_at": TIME, "license": NULLABLE_TEXT}, ["type", "ref", "observed_at"])
ERROR = obj({"code": {"enum": ["INVALID_INPUT", "MISSING_DATA", "UNSUPPORTED", "NETWORK_FAILURE",
    "VERSION_INCOMPATIBLE", "CONFIRMATION_REQUIRED", "CONFLICT", "BUDGET_EXHAUSTED", "INTERNAL_FAILURE"]},
             "message": TEXT, "retryable": {"type": "boolean"}, "details": {"type": "object"}})
RESULT = obj({"status": {"enum": ["success", "partial", "error"]}, "data": {},
              "sources": array(SOURCE), "versions": VERSIONS, "assumptions": STRINGS,
              "warnings": STRINGS, "missing_fields": STRINGS, "error": {"anyOf": [ERROR, {"type": "null"}]}},
             allOf=[{"if": {"properties": {"status": {"const": "error"}}},
                     "then": {"properties": {"error": ERROR}},
                     "else": {"properties": {"error": {"type": "null"}}}}])
MEASUREMENT = obj({"value": {"type": ["number", "null"]},
                   "unit": {"enum": ["flat", "ratio", "percent", "percentage_point", "speed", "av", "toughness", "count"]},
                   "state": {"enum": ["known", "unknown", "not_owned"]},
                   "precision": {"anyOf": [{"type": "number", "exclusiveMinimum": 0}, {"type": "null"}]}},
                  allOf=[{"if": {"properties": {"state": {"const": "known"}}},
                          "then": {"properties": {"value": {"type": "number"}}},
                          "else": {"properties": {"value": {"type": "null"}}}}])
FIELD = obj({"entity_id": TEXT, "field_id": ID, "quantity": MEASUREMENT, "source": SOURCE,
             "confirmed": {"type": "boolean"}, "basis": {"enum": ["base", "equipment_bonus", "public_panel", "record"]}})
ACCOUNT = obj({"account_id": ID, "snapshot_id": ID, "observed_at": TIME, "versions": VERSIONS,
               "roster_completeness": {"enum": ["partial", "complete", "unknown"]},
               "characters": array(obj({"character_id": TEXT, "form_id": TEXT, "ownership": {"enum": ["owned", "not_owned", "unknown"]}})),
               "equipment": array(obj({"instance_id": ID, "entity_id": TEXT, "owner_form_id": NULLABLE_TEXT})),
               "fields": array(FIELD)})
SCENARIO = obj({"scenario_id": ID, "mode": {"enum": ["moc", "pure_fiction", "apocalyptic_shadow", "anomaly_arbitration"]},
                "versions": VERSIONS, "valid_from": {"anyOf": [TIME, {"type": "null"}]},
                "valid_to": {"anyOf": [TIME, {"type": "null"}]}, "observed_at": TIME,
                "waves": array(obj({"wave": {"type": "integer", "minimum": 1}, "enemies": array(ID)})),
                "information_state": {"enum": ["official_verified", "official_disputed", "beta", "leak", "stale", "unknown"]},
                "evidence": {"enum": ["primary", "reproduced", "community", "hypothesis", "unknown"]},
                "coverage": {"enum": ["verified", "approximate", "unsupported", "unknown"]},
                "initial_resources": array(FIELD), "missing_fields": STRINGS, "sources": array(SOURCE)})
ENTRY = obj({"id": ID, "category": {"enum": ["combat", "characters", "basics"]}, "title": TEXT,
             "aliases": STRINGS, "version_min": TEXT, "version_max": TEXT,
             "information_state": {"enum": ["official_verified", "official_disputed", "beta", "leak", "stale", "unknown"]},
             "evidence": {"enum": ["primary", "reproduced", "community", "hypothesis", "unknown"]},
             "body_path": TEXT, "conditions": STRINGS, "exceptions": STRINGS,
             "sources": array(SOURCE, minItems=1), "verified_at": TIME, "license": TEXT})
PACKAGE = obj({"schema_version": {"const": 1}, "kind": {"const": "knowledge-content"},
               "version": {"type": "string", "pattern": "^\\d+\\.\\d+\\.\\d+$"},
               "compatibility": obj({"program_min": TEXT, "program_max": TEXT, "content_schema": {"const": 1}}),
               "entries": array(ENTRY, minItems=1, maxItems=1000),
               "files": array(obj({"path": TEXT, "sha256": SHA, "size": {"type": "integer", "minimum": 1, "maximum": 131072}}), maxItems=1000)})
ACTION = obj({"id": ID, "kind": {"const": "program"}, "target_version": TEXT, "package_sha256": SHA,
              "scope": {"const": "program-and-executable-rules"}, "scope_path": TEXT, "migrations": STRINGS,
              "state": {"enum": ["proposed", "confirmed", "consumed", "invalidated"]}, "created_at": TIME})


def main():
    for name, schema in {"tool-result": RESULT, "account-field": FIELD, "account-snapshot": ACCOUNT, "scenario": SCENARIO,
                         "knowledge-entry": ENTRY, "knowledge-package": PACKAGE, "action-request": ACTION}.items():
        schema = {"$schema": "https://json-schema.org/draft/2020-12/schema", **schema}
        (ROOT / "schemas" / f"{name}.schema.json").write_text(
            json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

