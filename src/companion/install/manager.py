from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import uuid

from companion.contracts import CompanionError, ErrorCode, canonical
from companion.domain.models import version_tuple
from companion.release.artifacts import MAX_ARTIFACT, digest, open_artifact
from companion.storage import SafeRoot
from companion.storage.paths import file_lock


class Installer:
    def __init__(self, root, data_dir, *, trusted_keys, allow_test=False, health_check=None, checkpoint=None):
        self.root = Path(os.path.abspath(root))
        self.data_dir = Path(os.path.abspath(data_dir))
        if self.root == self.data_dir or self.root in self.data_dir.parents or self.data_dir in self.root.parents:
            raise CompanionError(ErrorCode.INVALID_INPUT, "程序目录与个人数据目录必须互相独立")
        if self.root.parent == self.root or self.data_dir.parent == self.data_dir:
            raise CompanionError(ErrorCode.INVALID_INPUT, "不能使用磁盘根目录")
        self.trusted_keys, self.allow_test = trusted_keys, allow_test
        self.health_check = health_check or self._health_check
        self.checkpoint = checkpoint or (lambda phase: None)

    def _files(self):
        # Refuse to take ownership of arbitrary existing folders.
        if self.root.exists() and any(self.root.iterdir()) and not (self.root/"ownership.json").is_file():
            raise CompanionError(ErrorCode.CONFLICT, "程序目录非空且不属于本安装器")
        files = SafeRoot(self.root)
        marker = files.path("ownership.json")
        expected = {"owner": "hsr-companion-v1", "data_dir": str(self.data_dir)}
        if marker.exists():
            if json.loads(marker.read_bytes()) != expected:
                raise CompanionError(ErrorCode.CONFLICT, "程序目录所有权不匹配")
        else:
            files.write("ownership.json", canonical(expected))
        return files

    def state(self, files=None):
        files = files or self._files()
        path = files.path("install-state.json")
        if not path.exists():
            return None
        try:
            value = json.loads(path.read_bytes())
            if value["owner"] != "hsr-companion-v1" or value["data_dir"] != str(self.data_dir):
                raise ValueError()
            for item in (value.get("current"), value.get("previous")):
                if item is not None:
                    if len(item["digest"]) != 64 or any(c not in "0123456789abcdef" for c in item["digest"]):
                        raise ValueError()
            return value
        except (ValueError, KeyError, TypeError) as error:
            raise CompanionError(ErrorCode.CONFLICT, "安装状态无效或个人目录不匹配") from error

    @staticmethod
    def _database_backup(source, destination):
        destination.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(source.as_uri()+"?mode=ro", uri=True)) as live, closing(sqlite3.connect(destination)) as backup:
            live.backup(backup)

    def _health_check(self, version_dir, candidate_data):
        python = version_dir/"runtime/python.exe"
        command = [str(python), "-I", "-m", "companion.install.health", "--data-dir", str(candidate_data)]
        try:
            environment = os.environ.copy()
            environment.pop("PYTHONPATH", None)
            result = subprocess.run(command, cwd=version_dir, env=environment, capture_output=True, timeout=40,
                                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            if result.returncode or len(result.stdout) > 65536:
                raise ValueError()
            value = json.loads(result.stdout)
            if value.get("status") != "PASS":
                raise ValueError()
            return value
        except (OSError, ValueError, subprocess.TimeoutExpired) as error:
            raise CompanionError(ErrorCode.VERSION_INCOMPATIBLE, "候选版本自检或隔离迁移失败，旧版本保留") from error

    def _restore_locked(self, files):
        journal = files.path("transaction.json")
        if not journal.exists():
            return False
        entry = json.loads(journal.read_bytes())
        state = self.state(files)
        if entry.get("new_digest") != (state or {}).get("current", {}).get("digest"):
            backup = files.path(entry["backup_database"])
            if entry.get("had_database") and backup.is_file():
                SafeRoot(self.data_dir).write("personal/personal.sqlite3", backup.read_bytes())
            if entry.get("config_changed"):
                data = SafeRoot(self.data_dir)
                if entry.get("had_config"):
                    data.write("config.json", files.path(entry["backup_config"]).read_bytes())
                else:
                    data.path("config.json").unlink(missing_ok=True)
        files.write("last-transaction.json", canonical(dict(entry, recovered=True)))
        journal.unlink()
        return True

    def recover(self):
        files = self._files()
        data = SafeRoot(self.data_dir)
        with file_lock(files, "install.lock"), file_lock(data, "maintenance.lock", timeout=0):
            return {"recovered": self._restore_locked(files), "state": self.state(files)}

    def install(self, content, *, expected_sha256=None, authorization=None):
        if expected_sha256 and digest(content) != expected_sha256:
            raise CompanionError(ErrorCode.CONFLICT, "候选包与批准的指纹不一致")
        metadata, payload, identity = open_artifact(content, self.trusted_keys, allow_test=self.allow_test)
        if metadata["kind"] != "program" or metadata["target"] != "windows-x64" or "runtime/python.exe" not in payload:
            raise CompanionError(ErrorCode.INVALID_INPUT, "不是完整的 Windows 程序包")
        files = self._files()
        data = SafeRoot(self.data_dir)
        with file_lock(files, "install.lock"), file_lock(data, "maintenance.lock", timeout=0):
            self._restore_locked(files)
            state = self.state(files)
            fingerprint = digest(content)
            if state and state["current"]["digest"] == fingerprint:
                return {"state": "unchanged", "version": metadata["version"], "installed": False}
            if state:
                if version_tuple(metadata["version"]) <= version_tuple(state["current"]["version"]):
                    raise CompanionError(ErrorCode.VERSION_INCOMPATIBLE, "程序更新必须递增版本；恢复旧版请用明确的回滚操作")
                if not authorization or authorization.get("package_sha256") != fingerprint or authorization.get("scope_path") != str(self.root):
                    raise CompanionError(ErrorCode.CONFIRMATION_REQUIRED, "已有程序升级须消费匹配方案的确认")
            required = sum(len(body) for body in payload.values())*2 + 16*1024*1024
            if shutil.disk_usage(files.root).free < required:
                raise CompanionError(ErrorCode.BUDGET_EXHAUSTED, "磁盘可用空间不足，尚未切换版本")
            version_relative = f"versions/{fingerprint}"
            for name, body in payload.items():
                destination = files.path(f"{version_relative}/{name}")
                if destination.exists():
                    if destination.read_bytes() != body:
                        raise CompanionError(ErrorCode.CONFLICT, "已存在的不可变版本文件被修改")
                else:
                    files.write(f"{version_relative}/{name}", body, exclusive=True)
            files.write(f"{version_relative}/release-manifest.json", canonical(metadata))
            files.write(f"{version_relative}/release-artifact.json", content)
            transaction = uuid.uuid4().hex
            candidate_relative = f"backups/{transaction}/candidate"
            candidate = files.mkdir(candidate_relative)
            database = data.path("personal/personal.sqlite3")
            backup_relative = f"backups/{transaction}/original.sqlite3"
            entry = {"id": transaction, "new_digest": fingerprint, "backup_database": backup_relative,
                     "had_database": database.is_file(), "phase": "prepared"}
            source_config = metadata["inputs"].get("update_sources", {})
            if source_config:
                from companion.services.context import Context
                from companion.sources.http import public_url
                if set(source_config) != {"program_source", "knowledge_source"}:
                    raise CompanionError(ErrorCode.INVALID_INPUT, "签名包更新来源字段不允许")
                existing = Context(self.data_dir).config
                merged = dict(existing)
                for key, value in source_config.items():
                    merged.setdefault(key, public_url(value))
                config_path = data.path("config.json")
                entry.update(config_changed=merged != existing, had_config=config_path.exists(), backup_config=f"backups/{transaction}/config-before.json")
                if entry["config_changed"] and entry["had_config"]:
                    files.write(entry["backup_config"], config_path.read_bytes())
            if database.is_file():
                self._database_backup(database, files.path(backup_relative))
                files.write(f"{candidate_relative}/personal/personal.sqlite3", files.path(backup_relative).read_bytes())
            files.write("transaction.json", canonical(entry))
            try:
                self.checkpoint("prepared")
                health = self.health_check(files.path(version_relative), candidate)
                if health.get("status") != "PASS" or health.get("version") != metadata["version"]:
                    raise CompanionError(ErrorCode.VERSION_INCOMPATIBLE, "候选程序自报版本与已签名清单不一致")
                migrated = files.path(f"{candidate_relative}/personal/personal.sqlite3")
                if database.is_file() and migrated.is_file():
                    data.write("personal/personal.sqlite3", migrated.read_bytes())
                if entry.get("config_changed"):
                    data.write("config.json", canonical(merged))
                self.checkpoint("migrated")
                # Authorization is consumed only after verification, staging and self-check.
                if authorization and authorization.get("consume"):
                    authorization["consume"]()
                current = {"digest": fingerprint, "version": metadata["version"], "identity": identity}
                new_state = {"owner": "hsr-companion-v1", "schema_version": 1, "data_dir": str(self.data_dir),
                             "current": current, "previous": state["current"] if state else None,
                             "backup_database": backup_relative if database.is_file() else None,
                             "channel": metadata["channel"], "last_transaction": transaction}
                files.write("install-state.json", canonical(new_state))
                self.checkpoint("activated")
                files.write("last-transaction.json", canonical(dict(entry, phase="committed")))
                files.path("transaction.json").unlink()
                self._write_launcher(files)
                trust_path = data.path("release-trust.json")
                if not trust_path.exists():
                    data.write("release-trust.json", canonical({"schema_version": 1, "keys": self.trusted_keys}))
                return {"state": "installed", "installed": True, "version": metadata["version"],
                        "sha256": fingerprint, "health": health, "previous_retained": bool(state)}
            except BaseException:
                self._restore_locked(files)
                raise

    def _write_launcher(self, files):
        # All sessions execute a fixed immutable version; no PATH Python is used.
        text = ("param([Parameter(ValueFromRemainingArguments=$true)][string[]]$AssistantArgs)\n"
                "$ErrorActionPreference = 'Stop'\n"
                "$hsrRoot = $PSScriptRoot\n"
                "$hsrState = Get-Content -LiteralPath (Join-Path $hsrRoot 'install-state.json') -Raw -Encoding UTF8 | ConvertFrom-Json\n"
                "$hsrPython = Join-Path $hsrRoot ('versions/' + $hsrState.current.digest + '/runtime/python.exe')\n"
                "& $hsrPython -I -m companion.install.launcher --root $hsrRoot -- @AssistantArgs\nexit $LASTEXITCODE\n")
        files.write("启动助手.ps1", b"\xef\xbb\xbf"+text.encode("utf-8"))

    def rollback(self):
        files = self._files()
        data = SafeRoot(self.data_dir)
        with file_lock(files, "install.lock"), file_lock(data, "maintenance.lock", timeout=0), file_lock(files, "activity.lock", timeout=0):
            self._restore_locked(files)
            state = self.state(files)
            if not state or not state.get("previous"):
                raise CompanionError(ErrorCode.MISSING_DATA, "没有保留的上一程序版本")
            target = state["previous"]
            version_dir = files.path("versions/"+target["digest"])
            self.verify_version(target, files=files)
            # Test old code against today's database instead of restoring a stale personal backup.
            candidate = files.mkdir("rollback-check/"+uuid.uuid4().hex)
            database = data.path("personal/personal.sqlite3")
            if database.is_file():
                self._database_backup(database, candidate/"personal/personal.sqlite3")
            self.health_check(version_dir, candidate)
            state["current"], state["previous"] = target, state["current"]
            files.write("install-state.json", canonical(state))
            return {"state": "rolled_back", "version": target["version"], "personal_data_restored": False}

    def verify_version(self, item, *, files=None):
        files = files or self._files()
        relative = "versions/"+item["digest"]
        with files.path(relative+"/release-artifact.json").open("rb") as stream:
            content = stream.read(MAX_ARTIFACT+1)
        if digest(content) != item["digest"]:
            raise CompanionError(ErrorCode.CONFLICT, "保留的原程序包指纹发生变化")
        metadata, payload, _ = open_artifact(content, self.trusted_keys, allow_test=self.allow_test)
        if metadata["version"] != item["version"]:
            raise CompanionError(ErrorCode.CONFLICT, "保留版本与已签名原包不一致")
        for name, original in payload.items():
            if files.path(relative+"/"+name).read_bytes() != original:
                raise CompanionError(ErrorCode.CONFLICT, "保留的程序快照已被修改，拒绝执行")
        return files.path(relative)

    def uninstall(self, *, purge_data=False):
        files = self._files()
        state = self.state(files)
        if not state:
            raise CompanionError(ErrorCode.CONFLICT, "没有受管安装")
        data = SafeRoot(self.data_dir)
        with file_lock(files, "install.lock"), file_lock(files, "activity.lock", timeout=0), file_lock(data, "maintenance.lock", timeout=0):
            from companion.adapters.codex import uninstall_codex
            workspaces_path = files.path("workspaces.json")
            adapter_results = []
            for workspace in json.loads(workspaces_path.read_bytes()) if workspaces_path.is_file() else []:
                adapter_results.append(uninstall_codex(workspace))
            # Rename only the verified managed versions directory; keep the audit/state tombstone.
            versions = files.path("versions")
            retired = files.path("retired-"+uuid.uuid4().hex)
            if versions.exists():
                if not versions.resolve().is_relative_to(files.root) or not retired.parent.resolve() == files.root:
                    raise CompanionError(ErrorCode.INVALID_INPUT, "卸载路径越界")
                versions.rename(retired)
            files.write("uninstalled.json", canonical(dict(state, personal_data_preserved=not purge_data)))
            files.path("install-state.json").unlink()
            files.path("启动助手.ps1").unlink(missing_ok=True)
            if purge_data:
                # Explicit, separate choice; move aside rather than irreversibly delete.
                quarantine = self.data_dir.with_name(self.data_dir.name+".removed-"+uuid.uuid4().hex)
            else:
                quarantine = None
        if quarantine:
            if not self.data_dir.resolve().parent == quarantine.parent.resolve() or self.data_dir.parent == self.data_dir:
                raise CompanionError(ErrorCode.INVALID_INPUT, "个人目录清理目标不安全")
            self.data_dir.rename(quarantine)
        if retired.exists():
            # Check the exact tree and every descendant before recursively removing only this owned tree.
            if retired.parent.resolve() != files.root or not retired.name.startswith("retired-"):
                raise CompanionError(ErrorCode.INVALID_INPUT, "程序清理目录越界")
            native_retired = Path("\\\\?\\"+str(retired)) if os.name == "nt" else retired
            for node in native_retired.rglob("*"):
                if node.is_symlink() or getattr(node.lstat(), "st_file_attributes", 0) & 0x400:
                    raise CompanionError(ErrorCode.INVALID_INPUT, "待清理程序目录含链接，已停止删除")
            shutil.rmtree(native_retired)
        return {"state": "uninstalled", "personal_data_preserved": not purge_data,
                "data_quarantine": str(quarantine) if quarantine else None, "program_files_removed": True,
                "adapters": adapter_results}
