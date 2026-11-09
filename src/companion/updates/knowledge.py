"""Prepare a complete immutable generation before atomically replacing its pointer."""
import hashlib
import json
import time

from companion import PROGRAM_API_VERSION
from companion.contracts import CompanionError, ErrorCode, ToolResult, canonical
from companion.domain.models import version_tuple
from companion.knowledge.package import KnowledgePackage
from companion.knowledge.index import ensure_index
from companion.storage import SafeRoot
from companion.storage.paths import file_lock


class KnowledgeSync:
    def __init__(self, directory, *, source=None, clock=time.time, interval=21600, program_version=PROGRAM_API_VERSION):
        self.files = SafeRoot(directory)
        self.source, self.clock, self.interval = source, clock, interval
        self.program_version = program_version

    def _json(self, path):
        return json.loads(self.files.path(path).read_bytes())

    def _write(self, path, value):
        self.files.write(path, canonical(value))

    def _load_generation(self, digest):
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise CompanionError(ErrorCode.INVALID_INPUT, "知识生效指针无效")
        package = KnowledgePackage.decode(self.files.path(f"packages/{digest}/package.json").read_bytes())
        if package.fingerprint != digest:
            raise CompanionError(ErrorCode.CONFLICT, "知识代指纹不一致")
        if not package.compatible(self.program_version):
            raise CompanionError(ErrorCode.VERSION_INCOMPATIBLE, "已安装知识包不兼容")
        index = self._json(f"packages/{digest}/index.json")
        if index != self._index(package):
            raise CompanionError(ErrorCode.CONFLICT, "知识目录索引损坏")
        ensure_index(package, self.files, f"packages/{digest}/search-index.json")
        return package

    @staticmethod
    def _index(package):
        return [{"id": e["id"], "category": e["category"], "title": e["title"], "body_path": e["body_path"]}
                for e in package.manifest["entries"]]

    def _recover_locked(self):
        pointer = self.files.path("active.json")
        if not pointer.exists():
            return None, False
        try:
            state = self._json("active.json")
        except (ValueError, OSError):
            state = {}
        candidates = [(state.get("current"), False), (state.get("previous"), True)]
        backup = self.files.path("last-good.json")
        if backup.exists():
            try:
                candidates.append((self._json("last-good.json").get("current"), True))
            except (ValueError, OSError):
                pass
        for digest, recovered in candidates:
            if digest is None:
                continue
            try:
                package = self._load_generation(digest)
                if recovered:
                    self._write("active.json", {"current": digest, "previous": None})
                return package, recovered
            except (CompanionError, ValueError, OSError):
                continue
        raise CompanionError(ErrorCode.CONFLICT, "没有可恢复的有效知识包", retryable=True)

    def recover(self):
        with file_lock(self.files, "sync.lock"):
            package, recovered = self._recover_locked()
            return {"version": package.manifest["version"] if package else None, "recovered": recovered}

    def current(self):
        with file_lock(self.files, "sync.lock"):
            package, _ = self._recover_locked()
            return package

    def sync(self, *, force=False, offline=False, checkpoint=None):
        try:
            with file_lock(self.files, "sync.lock"):
                current, recovered = self._recover_locked()
                current_version = current.manifest["version"] if current else None
                state_path = self.files.path("check.json")
                state = self._json("check.json") if state_path.exists() else {}
                if self.source is None:
                    return ToolResult(status="partial", data={"state": "unconfigured", "version": current_version, "latest": False},
                                      warnings=["尚未配置维护者发布源；无法确认是否最新"])
                if not force and self.clock() - state.get("checked_at", -self.interval) < self.interval:
                    return ToolResult(data={"state": "cached", "version": current_version,
                                            "latest": False, "last_verified_at": state.get("checked_at")},
                                      warnings=["本次未重新检查远端"])
                manifest = self.source.manifest("knowledge", offline=offline)
                if current and manifest["version"] == current_version:
                    if manifest.get("content_sha256", manifest["sha256"]) != hashlib.sha256(current.encode()).hexdigest():
                        raise CompanionError(ErrorCode.CONFLICT, "同一知识版本的指纹发生变化")
                    self._write("check.json", {"checked_at": self.clock(), "version": current_version})
                    return ToolResult(data={"state": "unchanged", "version": current_version, "latest": True},
                                      warnings=["已恢复上一有效知识包"] if recovered else [])
                if current and version_tuple(manifest["version"]) < version_tuple(current_version):
                    raise CompanionError(ErrorCode.VERSION_INCOMPATIBLE, "拒绝发布源知识降级")
                content = self.source.package(manifest, offline=offline)
                self.files.write("staging.json", content)
                package = KnowledgePackage.decode(content)
                if package.manifest["version"] != manifest["version"]:
                    raise CompanionError(ErrorCode.INVALID_INPUT, "发布清单与知识版本不一致")
                if not package.compatible(self.program_version):
                    raise CompanionError(ErrorCode.VERSION_INCOMPATIBLE, "知识包需要不同程序版本；程序不会自动升级")
                digest = package.fingerprint
                self.files.mkdir(f"packages/{digest}")
                self.files.write(f"packages/{digest}/package.json", package.encode())
                self._write(f"packages/{digest}/index.json", self._index(package))
                ensure_index(package, self.files, f"packages/{digest}/search-index.json")
                self._load_generation(digest)
                if checkpoint:
                    checkpoint("prepared")
                if current:
                    self._write("last-good.json", {"current": current.fingerprint})
                self._write("active.json", {"current": digest, "previous": current.fingerprint if current else None})
                if checkpoint:
                    checkpoint("activated")
                self._write("check.json", {"checked_at": self.clock(), "version": manifest["version"]})
                return ToolResult(data={"state": "updated", "version": manifest["version"], "latest": True},
                                  warnings=["仅与维护者发布物一致；不代表覆盖游戏最新补丁"])
        except CompanionError as error:
            return ToolResult.failure(error, data={"state": "failed", "latest": False})
        except (OSError, ValueError) as error:
            return ToolResult.failure(CompanionError(ErrorCode.NETWORK_FAILURE, "知识同步失败，保留已安装数据", retryable=True),
                                      data={"state": "failed", "latest": False})

