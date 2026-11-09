"""Exclude private fields instead of guessing which free text is sensitive."""
import hashlib
import json
from pathlib import Path
import platform
import re
import uuid
from urllib.parse import urlsplit
import zipfile

from companion import __version__
from companion.contracts import CompanionError, ErrorCode, canonical
from companion.storage import SafeRoot
from companion.storage.database import now
from companion.storage.paths import file_lock

OPERATIONS = {"public_source", "public_uid", "release_index", "release_artifact"}
OUTCOMES = {"attempt", "success", "failure", "http_error"}


def network_event(url, operation, outcome, *, status=None):
    host = urlsplit(url).hostname or "invalid"
    if not re.fullmatch(r"[A-Za-z0-9.-]{1,253}", host):
        host = "invalid"
    if operation not in OPERATIONS or outcome not in OUTCOMES:
        raise CompanionError(ErrorCode.INVALID_INPUT, "诊断事件类型不允许")
    event = {"at": now(), "destination_domain": host.lower(), "operation": operation, "outcome": outcome}
    if type(status) is int and 100 <= status <= 599:
        event["http_status"] = status
    return event


class NetworkAudit:
    def __init__(self, directory):
        self.files = SafeRoot(directory)

    def record(self, event):
        # Callers cannot smuggle query strings, bodies, account IDs, headers or tokens into logs.
        allowed = {"at", "destination_domain", "operation", "outcome", "http_status"}
        clean = {k: v for k, v in event.items() if k in allowed}
        checked = network_event("https://"+clean.get("destination_domain", "invalid"), clean.get("operation"), clean.get("outcome"), status=clean.get("http_status"))
        with file_lock(self.files, "network.lock"):
            path = self.files.path("network.json")
            events = json.loads(path.read_bytes()) if path.is_file() and path.stat().st_size < 512000 else []
            self.files.write("network.json", canonical((events[-499:]+[checked])))


def prepare_diagnostics(data_dir):
    root = SafeRoot(data_dir)
    identifier = uuid.uuid4().hex
    relative = "diagnostics/drafts/"+identifier
    root.mkdir(relative)
    report = {"schema_version": 1, "program_version": __version__, "python_version": platform.python_version(),
              "platform": platform.system(), "platform_release": platform.release(), "machine": platform.machine(),
              "contains_account_or_research": False, "uploaded": False}
    audit = root.path("diagnostics/network.json")
    events = json.loads(audit.read_bytes()) if audit.is_file() and audit.stat().st_size < 512000 else []
    # Recreate every event through the allowlist, even if the local audit file was edited.
    report["network"] = [network_event("https://"+e.get("destination_domain", "invalid"), e.get("operation"), e.get("outcome"), status=e.get("http_status")) for e in events[-100:]]
    body = canonical(report)
    root.write(relative+"/diagnostics.json", body)
    plan = {"schema_version": 1, "id": identifier, "sharing_state": "review_required", "uploaded": False,
            "files": [{"name": "diagnostics.json", "size": len(body), "sha256": hashlib.sha256(body).hexdigest()}],
            "excluded": ["UID", "account_id", "research", "snapshots", "source bodies", "credentials", "paths", "configuration"]}
    root.write(relative+"/share-plan.json", canonical(plan))
    return {"plan": str(root.path(relative+"/share-plan.json")), "review_directory": str(root.path(relative)), **plan}


def export_diagnostics(plan_path, output):
    plan_path = Path(plan_path)
    files = SafeRoot(plan_path.parent)
    if plan_path.name != "share-plan.json" or plan_path.stat().st_size > 65536:
        raise CompanionError(ErrorCode.INVALID_INPUT, "诊断分享清单无效")
    plan = json.loads(plan_path.read_bytes())
    if len(plan.get("files", [])) != 1 or plan["files"][0]["name"] != "diagnostics.json":
        raise CompanionError(ErrorCode.INVALID_INPUT, "诊断只允许固定的已审阅去敏报告")
    row = plan["files"][0]
    content = files.path(row["name"]).read_bytes()
    if len(content) > 131072 or len(content) != row["size"] or hashlib.sha256(content).hexdigest() != row["sha256"]:
        raise CompanionError(ErrorCode.CONFLICT, "报告在生成待分享清单后发生变化")
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as stream, zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("diagnostics.json", content)
    return {"output": str(output.absolute()), "uploaded": False, "files": [row["name"]]}
