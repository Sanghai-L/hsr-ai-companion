"""Replay with an authenticated retained program, never with silently changed rules."""
from contextlib import nullcontext
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

from companion.contracts import CompanionError, ErrorCode, ToolResult, canonical
from companion.install import Installer
from companion.release.signing import load_trust
from companion.storage import SafeRoot
from companion.storage.paths import file_lock


def archived_replay(store, account_id, experiment_id, payload):
    location = os.environ.get("HSR_COMPANION_INSTALL_ROOT")
    if not location or os.environ.get("HSR_ARCHIVE_REPLAY_DEPTH"):
        raise CompanionError(ErrorCode.VERSION_INCOMPATIBLE, "原执行快照不可用；不能用新规则冒充原条件重算")
    data_dir = store.files.root.parent
    keys = load_trust(SafeRoot(data_dir).path("release-trust.json"))
    files = SafeRoot(location)
    state = json.loads(files.path("install-state.json").read_bytes())
    manager = Installer(files.root, data_dir, trusted_keys=keys, allow_test=state["channel"] == "test")
    expected = payload["result"]["implementation_fingerprint"]
    target = None
    with file_lock(files, "activity.lock", shared=True):
        directory = files.path("versions")
        for path in sorted(directory.iterdir()):
            if not re.fullmatch(r"[0-9a-f]{64}", path.name):
                continue
            manifest_path = files.path("versions/"+path.name+"/release-manifest.json")
            if not manifest_path.is_file() or manifest_path.stat().st_size > 4*1024*1024:
                continue
            metadata = json.loads(manifest_path.read_bytes())
            if metadata["version"] != payload["versions"]["engine"]:
                continue
            prefix = "runtime/Lib/site-packages/companion/"
            python_files = {row["path"][len(prefix):]: row["sha256"] for row in metadata["files"]
                            if row["path"].startswith(prefix) and row["path"].endswith(".py")}
            if hashlib.sha256(canonical(python_files)).hexdigest() != expected:
                continue
            target = manager.verify_version({"digest": path.name, "version": metadata["version"]})
            break
        if target is None:
            raise CompanionError(ErrorCode.VERSION_INCOMPATIBLE, "没有匹配原实验代码指纹的已验证保留版本")
        environment = {k: os.environ[k] for k in ("SYSTEMROOT", "WINDIR", "TEMP", "TMP") if k in os.environ}
        environment.update(PYTHONUTF8="1", PYTHONIOENCODING="utf-8", HSR_ARCHIVE_REPLAY_DEPTH="1")
        command = [str(target/"runtime/python.exe"), "-I", "-m", "companion", "--data-dir", str(data_dir), "--offline", "call", "experiment_replay", "--input", "-"]
        try:
            process = subprocess.run(command, input=canonical({"account_id": account_id, "experiment_id": experiment_id}),
                                     capture_output=True, timeout=30, env=environment,
                                     creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            if len(process.stdout) > 65536:
                raise ValueError()
            result = ToolResult.from_dict(json.loads(process.stdout))
            if process.returncode or result.status != "success" or not result.data.get("same_result"):
                raise CompanionError(ErrorCode.VERSION_INCOMPATIBLE, "原程序快照拒绝重算，保留历史输入", details={
                    "original_exit_code": process.returncode, "original_error_code": (result.error or {}).get("code")})
        except (ValueError, OSError, subprocess.TimeoutExpired) as error:
            raise CompanionError(ErrorCode.VERSION_INCOMPATIBLE, "原程序快照重算未通过，保留历史实验与个人资料") from error
    result.data["archived_program"] = {"version": payload["versions"]["engine"], "sha256": target.name,
                                       "verified": True, "offline": True}
    result.warnings.append("本次使用原程序及原输入重算；不把新规则结果写回旧实验")
    return result
