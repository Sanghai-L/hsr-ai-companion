"""Signed manifest and deterministic ZIP payload with a strict file inventory."""
import base64
import hashlib
import io
import json
from pathlib import PurePosixPath
import re
import stat
import zipfile

from companion.contracts import CompanionError, ErrorCode, canonical, validate
from companion.knowledge.package import unique_object
from companion.release.signing import sign, verify
from companion.storage import SafeRoot

MAX_ARTIFACT = 96 * 1024 * 1024
MAX_EXPANDED = 256 * 1024 * 1024
MAX_FILES = 6000


def digest(content):
    return hashlib.sha256(content).hexdigest()


def safe_name(name):
    # Use exactly the same Windows rules as the eventual writer, without creating a directory.
    from pathlib import PureWindowsPath
    from companion.storage.paths import _RESERVED
    parts = name.split("/") if isinstance(name, str) else []
    if (not parts or "\\" in name or PureWindowsPath(name).drive or name.startswith("/") or any(
            not p or p in {".", ".."} or p.endswith((".", " ")) or _RESERVED.match(p) or
            any(ord(c) < 32 or c in ':<>"|?*' for c in p) for p in parts)):
        raise CompanionError(ErrorCode.INVALID_INPUT, "发布包包含非法文件路径")
    return name


def inventory(files):
    names = [safe_name(n) for n in files]
    if len(names) > MAX_FILES or len({n.casefold() for n in names}) != len(names):
        raise CompanionError(ErrorCode.INVALID_INPUT, "发布文件重复或过多")
    folded = {n.casefold() for n in names}
    if any(str(p).casefold() in folded for n in names for p in PurePosixPath(n).parents if str(p) != "."):
        raise CompanionError(ErrorCode.INVALID_INPUT, "发布文件与目录路径冲突")
    if sum(len(c) for c in files.values()) > MAX_EXPANDED:
        raise CompanionError(ErrorCode.INVALID_INPUT, "发布包展开大小超限")
    return [{"path": n, "size": len(files[n]), "sha256": digest(files[n])} for n in sorted(names)]


def zip_files(files):
    output = io.BytesIO()
    inventory(files)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, content in sorted(files.items()):
            info = zipfile.ZipInfo(name, (2020, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, content)
    return output.getvalue()


def make_artifact(files, *, kind, version, private, channel="test", inputs=None):
    from companion.domain.models import version_tuple
    version_tuple(version)
    listing = inventory(files)
    payload = zip_files(files) if kind == "program" else files["package.json"]
    manifest = {"schema_version": 1, "kind": kind, "version": version, "target": "windows-x64" if kind == "program" else "data",
                "channel": channel, "files": listing, "payload_sha256": digest(payload), "payload_size": len(payload),
                "inputs": inputs or {}}
    validate("release.schema.json", manifest)
    result = canonical({"manifest": manifest, "signature": sign(manifest, private), "payload": base64.b64encode(payload).decode()})
    if len(result) > MAX_ARTIFACT:
        raise CompanionError(ErrorCode.INVALID_INPUT, "发布包超过大小预算")
    return result


def open_artifact(content, trusted_keys, *, allow_test=False):
    if len(content) > MAX_ARTIFACT:
        raise CompanionError(ErrorCode.INVALID_INPUT, "发布包超过读取预算")
    try:
        value = json.loads(content, object_pairs_hook=unique_object)
        if set(value) != {"manifest", "signature", "payload"}:
            raise ValueError()
        manifest = validate("release.schema.json", value["manifest"])
        identity = verify(manifest, value["signature"], trusted_keys, allow_test=allow_test)
        payload = base64.b64decode(value["payload"], validate=True)
        if digest(payload) != manifest["payload_sha256"] or len(payload) != manifest["payload_size"]:
            raise ValueError()
        files = {}
        if manifest["kind"] == "program":
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                members = archive.infolist()
                if len(members) > MAX_FILES or sum(m.file_size for m in members) > MAX_EXPANDED:
                    raise ValueError()
                seen = set()
                for member in members:
                    name = safe_name(member.filename)
                    if name.casefold() in seen or member.is_dir() or stat.S_ISLNK(member.external_attr >> 16) or member.flag_bits & 1:
                        raise ValueError()
                    seen.add(name.casefold())
                    files[name] = archive.read(member)
        else:
            files = {"package.json": payload}
        if inventory(files) != manifest["files"]:
            raise ValueError()
        return manifest, files, identity
    except (ValueError, KeyError, TypeError, zipfile.BadZipFile, RuntimeError, OSError) as error:
        raise CompanionError(ErrorCode.INVALID_INPUT, "发布包结构、文件清单或完整性无效") from error


def release_pointer(content, artifact, private):
    value = json.loads(content)
    manifest = value["manifest"]
    document = {"kind": manifest["kind"], "version": manifest["version"], "sha256": digest(content), "size": len(content),
                "artifact": artifact, "channel": manifest["channel"], "content_sha256": manifest["payload_sha256"]}
    return canonical({"release": document, "signature": sign(document, private)})


def write_release(directory, content, name, private):
    files = SafeRoot(directory)
    safe_name(name)
    if "/" in name or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}\.json", name):
        raise CompanionError(ErrorCode.INVALID_INPUT, "发布文件名无效")
    files.write(name, content)
    files.write("release.json", release_pointer(content, name, private))
    return {"artifact": str(files.path(name)), "sha256": digest(content), "size": len(content)}
