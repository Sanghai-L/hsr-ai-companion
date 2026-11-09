"""Three layers: immutable raw response, remote facts, manual effective fields."""
import copy
import uuid

from companion.storage.database import now


def merge(previous, remote):
    if previous is None:
        value = copy.deepcopy(remote)
        value["snapshot_id"] = uuid.uuid4().hex
        return value, {"added": [f["entity_id"] + "." + f["field_id"] for f in remote["fields"]], "changed": [], "preserved_missing": [], "manual_conflicts": []}
    fields = {(f["entity_id"], f["field_id"]): f for f in previous["fields"]}
    diff = {"added": [], "changed": [], "preserved_missing": [], "manual_conflicts": []}
    remote_keys = set()
    for incoming in remote["fields"]:
        key = (incoming["entity_id"], incoming["field_id"])
        remote_keys.add(key)
        old = fields.get(key)
        name = ".".join(key)
        if old and incoming["quantity"]["state"] == "unknown" and old["quantity"]["state"] != "unknown":
            diff["preserved_missing"].append(name)
            continue
        if old and old["source"]["type"] in {"manual", "synthetic"}:
            if incoming["quantity"] != old["quantity"]:
                diff["manual_conflicts"].append({"field": name, "manual": old["quantity"], "remote": incoming["quantity"], "resolution": "manual_preserved"})
            continue
        if old is None:
            diff["added"].append(name)
        elif old["quantity"] != incoming["quantity"]:
            diff["changed"].append({"field": name, "old": old["quantity"], "new": incoming["quantity"]})
        fields[key] = incoming
    diff["preserved_missing"] += [".".join(k) for k in fields if k not in remote_keys]
    characters = {(c["character_id"], c["form_id"]): c for c in previous["characters"]}
    characters.update({(c["character_id"], c["form_id"]): c for c in remote["characters"]})
    # These are observations, not a current inventory. Old missing observations remain dated in field sources.
    equipment = {e["instance_id"]: e for e in previous["equipment"]}
    equipment.update({e["instance_id"]: e for e in remote["equipment"]})
    return {**previous, "snapshot_id": uuid.uuid4().hex, "observed_at": now(), "roster_completeness": "partial",
            "characters": list(characters.values()), "equipment": list(equipment.values()), "fields": list(fields.values())}, diff
