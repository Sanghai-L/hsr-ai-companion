"""Account-scoped immutable comparison inputs, stored in the existing transaction."""
import json
import uuid

from companion.contracts import CompanionError, ErrorCode, ToolResult, canonical
from companion.storage.database import identifier, now
from companion.simulation.compare import compare
from companion.simulation.rotation import digest, prepare


def save(store, account_id, request):
    store.require_account(account_id)
    value = prepare(request)
    result = compare(value)
    experiment_id = "cmp-" + uuid.uuid4().hex
    payload = {"kind": "representative_comparison", "input": value, "result": result.data,
               "result_fingerprint": digest(result.data), "versions": result.versions,
               "assumptions": result.assumptions, "warnings": result.warnings}
    with store.transaction() as connection:
        store.require_account(account_id, connection)
        connection.execute("INSERT INTO experiments(id,account_id,payload,input_sha256,created_at) VALUES(?,?,?,?,?)",
                           (experiment_id, account_id, canonical(payload).decode(), digest(value), now()))
    return ToolResult(status=result.status, data={"experiment_id": experiment_id, "comparison": result.data},
                      sources=result.sources, versions=result.versions, assumptions=result.assumptions,
                      warnings=result.warnings, missing_fields=result.missing_fields)


def replay(store, account_id, experiment_id):
    store.require_account(account_id)
    identifier(experiment_id)
    with store.connection() as connection:
        row = connection.execute("SELECT payload,input_sha256 FROM experiments WHERE account_id=? AND id=?",
                                 (account_id, experiment_id)).fetchone()
    if row is None:
        raise CompanionError(ErrorCode.MISSING_DATA, "此账号没有该比较记录")
    try:
        payload = json.loads(row["payload"])
        if payload["kind"] != "representative_comparison" or digest(payload["input"]) != row["input_sha256"] or digest(payload["result"]) != payload["result_fingerprint"]:
            raise ValueError()
    except (ValueError, KeyError, TypeError):
        raise CompanionError(ErrorCode.CONFLICT, "保存的比较记录损坏；保留原记录")
    from companion import __version__
    from companion.simulation.rotation import METHOD, implementation_fingerprint, mechanics
    if (payload["versions"]["engine"] != __version__ or payload["versions"]["rules"] != METHOD or
            payload["result"]["mechanics_fingerprint"] != digest(mechanics()) or
            payload["result"].get("implementation_fingerprint") != implementation_fingerprint()):
        from companion.experiments.archive import archived_replay
        return archived_replay(store, account_id, experiment_id, payload)
    result = compare(payload["input"])
    # Timing can change only a budget-truncated result; never call that deterministic replay.
    same = digest(result.data) == payload["result_fingerprint"]
    return ToolResult(status="success" if same and result.status == "success" else "partial",
                      data={"experiment_id": experiment_id, "recomputed_from_start": True, "same_result": same,
                            "comparison": result.data}, sources=result.sources, versions=result.versions,
                      assumptions=result.assumptions, warnings=result.warnings, missing_fields=result.missing_fields)
