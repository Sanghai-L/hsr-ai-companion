"""Read only the configured maintainer source; never accept an Agent URL per call."""
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urljoin, urlsplit
import urllib.request

from companion.contracts import CompanionError, ErrorCode
from companion.domain.models import version_tuple
from companion.knowledge.package import MAX_PACKAGE, unique_object
from companion.storage import SafeRoot
from companion.release.artifacts import MAX_ARTIFACT, open_artifact
from companion.release.signing import verify


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise CompanionError(ErrorCode.NETWORK_FAILURE, "发布源重定向被拒绝", retryable=True)


class ReleaseSource:
    def __init__(self, location, *, trusted_keys=None, require_signature=False, allow_test=False, audit=None):
        self.location = str(location)
        self.trusted_keys = trusted_keys or []
        self.require_signature, self.allow_test = require_signature, allow_test
        self.audit = audit
        parsed = urlsplit(self.location)
        self.remote = parsed.scheme == "https"
        if self.remote:
            from companion.sources.http import public_url
            self.location = public_url(self.location)
            if not parsed.hostname or parsed.username or parsed.password or parsed.fragment or parsed.query:
                raise CompanionError(ErrorCode.INVALID_INPUT, "发布源 URL 格式不允许")
            self.local = None
        else:
            if not Path(self.location).is_absolute():
                raise CompanionError(ErrorCode.INVALID_INPUT, "本地发布源必须为绝对路径")
            if not Path(self.location).is_dir():
                raise CompanionError(ErrorCode.MISSING_DATA, "本地维护者发布源不存在")
            self.local = SafeRoot(self.location)

    def read(self, name, limit, *, offline=False):
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,119}\.json", name):
            raise CompanionError(ErrorCode.INVALID_INPUT, "发布文件名非法")
        if self.remote:
            if offline:
                raise CompanionError(ErrorCode.NETWORK_FAILURE, "离线模式未检查远端", retryable=True)
            url = self.location if name == "release.json" else urljoin(self.location, name)
            try:
                from companion.sources.http import fetch
                response = fetch(url, timeout=10, max_bytes=limit, audit=self.audit, operation="release_index" if name == "release.json" else "release_artifact")
                if response.status != 200:
                    raise CompanionError(ErrorCode.NETWORK_FAILURE, "发布源返回错误", retryable=True)
                content = response.body
            except (OSError, ValueError) as error:
                raise CompanionError(ErrorCode.NETWORK_FAILURE, "无法读取维护者发布源", retryable=True) from error
        else:
            with self.local.path(name).open("rb") as stream:
                content = stream.read(limit + 1)
        if len(content) > limit:
            raise CompanionError(ErrorCode.INVALID_INPUT, "发布内容超限")
        return content

    def manifest(self, kind, *, offline=False):
        try:
            value = json.loads(self.read("release.json", 65536, offline=offline), object_pairs_hook=unique_object)
        except (OSError, ValueError) as error:
            raise CompanionError(ErrorCode.NETWORK_FAILURE, "发布清单不可用", retryable=True) from error
        signed = isinstance(value, dict) and set(value) == {"release", "signature"}
        if signed:
            verify(value["release"], value["signature"], self.trusted_keys, allow_test=self.allow_test)
            value = value["release"]
        elif self.require_signature:
            raise CompanionError(ErrorCode.INVALID_INPUT, "发布索引没有可信签名")
        required = {"kind", "version", "sha256", "size", "artifact"} | ({"channel", "content_sha256"} if signed else set())
        if (not isinstance(value, dict) or set(value) != required or value["kind"] != kind or
                not isinstance(value["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", value["sha256"]) or
                type(value["size"]) is not int or not 0 < value["size"] <= (MAX_ARTIFACT if signed else MAX_PACKAGE) or
                not isinstance(value["artifact"], str) or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,119}\.json", value["artifact"])):
            raise CompanionError(ErrorCode.INVALID_INPUT, "发布清单不符合合同")
        version_tuple(value["version"])
        if signed and not re.fullmatch(r"[0-9a-f]{64}", value.get("content_sha256", "")):
            raise CompanionError(ErrorCode.INVALID_INPUT, "发布内容指纹无效")
        if signed:
            value = dict(value, signature_verified=True)
        return value

    def package(self, manifest, *, offline=False):
        content = self.read(manifest["artifact"], manifest["size"], offline=offline)
        if len(content) != manifest["size"] or hashlib.sha256(content).hexdigest() != manifest["sha256"]:
            raise CompanionError(ErrorCode.INVALID_INPUT, "发布包指纹或大小不匹配")
        if manifest.get("signature_verified"):
            metadata, files, _ = open_artifact(content, self.trusted_keys, allow_test=self.allow_test)
            if (metadata["version"] != manifest["version"] or metadata["kind"] != manifest["kind"] or
                    metadata["channel"] != manifest["channel"] or metadata["payload_sha256"] != manifest["content_sha256"]):
                raise CompanionError(ErrorCode.INVALID_INPUT, "发布索引与包内容不一致")
            return files["package.json"] if manifest["kind"] == "knowledge" else content
        return content

