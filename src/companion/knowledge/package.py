"""Deterministic JSON content bundle: never extract arbitrary archive members."""
from dataclasses import dataclass
import hashlib
import json
import re

from companion import PROGRAM_API_VERSION
from companion.contracts import CompanionError, ErrorCode, canonical, validate
from companion.domain.models import version_tuple
from companion.storage import SafeRoot

MAX_PACKAGE = 2 * 1024 * 1024
MAX_BODY = 128 * 1024
CATEGORIES = {"combat", "battle", "characters", "basics"}
BODY_PATH = re.compile(r"^(combat|battle|characters|basics)/([a-zA-Z0-9][a-zA-Z0-9_-]{0,79})\.md$")


def reject(message):
    raise CompanionError(ErrorCode.INVALID_INPUT, message)


def safe_body(path, text):
    match = BODY_PATH.fullmatch(path)
    if not match or match[2].lower() in {"agents", "claude", "skill", "instructions"}:
        reject("知识包只允许三类目录中的普通内容文件")
    if not isinstance(text, str) or not text or len(text.encode("utf-8")) > MAX_BODY:
        reject("知识正文为空或超限")
    if "\x00" in text or re.search(r"```\s*(python|bash|sh|powershell|javascript|js|lua|exec|dsl)\b", text, re.I):
        reject("知识包不接受可执行脚本或 DSL")


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            reject("JSON 存在重复字段")
        result[key] = value
    return result


@dataclass(frozen=True)
class KnowledgePackage:
    manifest: dict
    bodies: dict

    def encode(self):
        return canonical({"manifest": self.manifest, "bodies": self.bodies})

    @property
    def fingerprint(self):
        return hashlib.sha256(self.encode()).hexdigest()

    def compatible(self, program_version=PROGRAM_API_VERSION):
        bounds = self.manifest["compatibility"]
        return version_tuple(bounds["program_min"]) <= version_tuple(program_version) <= version_tuple(bounds["program_max"])

    @classmethod
    def decode(cls, content: bytes):
        if len(content) > MAX_PACKAGE:
            reject("知识包超过 2 MiB 限额")
        try:
            document = json.loads(content, object_pairs_hook=unique_object)
        except (ValueError, UnicodeDecodeError):
            reject("知识包 JSON 无效")
        if not isinstance(document, dict) or set(document) != {"manifest", "bodies"} or not isinstance(document["bodies"], dict):
            reject("知识包封装不符合合同")
        manifest, bodies = document["manifest"], document["bodies"]
        validate("knowledge-package.schema.json", manifest)
        version_tuple(manifest["version"])
        bounds = manifest["compatibility"]
        if version_tuple(bounds["program_min"]) > version_tuple(bounds["program_max"]):
            reject("知识包兼容范围颠倒")
        ids, paths = set(), set()
        for entry in manifest["entries"]:
            key, path = entry["id"], entry["body_path"]
            if key.casefold() in ids or path.casefold() in paths:
                reject("重复知识 ID 或内容路径")
            ids.add(key.casefold())
            paths.add(path.casefold())
            if path != entry["category"] + "/" + key + ".md" or path not in bodies:
                reject("知识分类／ID／文件路径不一致")
            safe_body(path, bodies[path])
            if (entry["category"] == "battle" or any(k in entry for k in ("namespace", "entities", "claims"))) and version_tuple(bounds["program_min"]) < (0, 1, 1):
                reject("扩展知识字段至少需要程序 0.1.1；不能向旧版宣称兼容")
            namespace = entry.get("namespace", "release")
            if (entry["information_state"] in {"beta", "leak"}) != (namespace in {"beta", "leak"}):
                reject("正式知识与未上线资料必须使用不同命名空间")
            if namespace in {"beta", "leak"} and (entry["information_state"] != namespace or not key.startswith(namespace + "-")):
                reject("未上线知识 ID 与状态必须保留命名空间")
        if set(bodies) != {e["body_path"] for e in manifest["entries"]}:
            reject("存在未登记的知识正文")
        file_paths = set()
        for item in manifest["files"]:
            path = item["path"]
            if path in file_paths or path not in bodies:
                reject("重复或缺失的知识文件")
            file_paths.add(path)
            body_bytes = bodies[path].encode("utf-8")
            if len(body_bytes) != item["size"] or hashlib.sha256(body_bytes).hexdigest() != item["sha256"]:
                reject("知识文件完整性校验失败")
        if set(bodies) != file_paths or len(paths) != len(file_paths):
            reject("存在未登记的知识文件")
        package = cls(manifest, bodies)
        if package.encode() != content:
            reject("知识包必须采用构建器的规范化 JSON 编码")
        return package


def build_package(source, *, version, program_min=None, program_max="0.1.99"):
    root = SafeRoot(source)
    entries, bodies = [], {}
    seen = set()
    for path in sorted(root.root.rglob("*")):
        relative = path.relative_to(root.root).as_posix()
        checked = root.path(relative)
        if checked.is_dir():
            if relative not in CATEGORIES:
                reject("知识源包含未知目录")
            continue
        if checked.suffix == ".md":
            body = checked.read_text(encoding="utf-8")
            safe_body(relative, body)
            bodies[relative] = body
        elif relative == "sources.json":
            # Maintainer provenance registry, never a runtime instruction or executable payload.
            registry = json.loads(checked.read_text(encoding="utf-8"), object_pairs_hook=unique_object)
            if not isinstance(registry, dict) or registry.get("schema_version") != 1 or not isinstance(registry.get("sources"), list):
                reject("知识来源登记格式错误")
        elif checked.suffix == ".json" and checked.parent.name in CATEGORIES:
            entry = json.loads(checked.read_text(encoding="utf-8"), object_pairs_hook=unique_object)
            validate("knowledge-entry.schema.json", entry)
            if relative != f"{entry['category']}/{entry['id']}.json":
                reject("知识元数据路径不匹配")
            entries.append(entry)
            seen.add(relative)
        else:
            reject("知识源包含脚本、Agent 指令或未知文件")
    requires_extended = any(e["category"] == "battle" or any(k in e for k in ("namespace", "entities", "claims")) for e in entries)
    if program_min is None:
        program_min = "0.1.1" if requires_extended else "0.1.0"
    manifest = {"schema_version": 1, "kind": "knowledge-content", "version": version,
                "compatibility": {"program_min": program_min, "program_max": program_max, "content_schema": 1},
                "entries": sorted(entries, key=lambda e: e["id"]),
                "files": [{"path": path, "sha256": hashlib.sha256(body.encode()).hexdigest(), "size": len(body.encode())}
                          for path, body in sorted(bodies.items())]}
    return KnowledgePackage.decode(canonical({"manifest": manifest, "bodies": bodies}))

