"""Offline Windows build from an explicit runtime inventory and a project wheel."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

from companion import __version__
from companion.contracts import canonical
from companion.release.artifacts import make_artifact, write_release
from companion.release.private_key import unlock
from companion.release.signing import test_key, load_trust

ROOT = Path(__file__).resolve().parents[1]


def build(output, *, runtime, private, channel, version=__version__, update_base=None):
    if version != __version__:
        raise ValueError("发布版本必须与项目元数据相同")
    import tomllib
    if tomllib.loads((ROOT/"pyproject.toml").read_text(encoding="utf-8"))["project"]["version"] != version:
        raise ValueError("项目版本不一致")
    lock = json.loads((ROOT/"manifests/windows-runtime.lock.json").read_bytes())
    deps = hashlib.sha256((ROOT/"requirements-runtime.lock").read_bytes()).hexdigest()
    if deps != lock["dependency_lock_sha256"]:
        raise ValueError("运行依赖锁变化，须重新准备并验证运行时")
    actual = {p.relative_to(runtime).as_posix() for p in runtime.rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"}
    if actual != {r["path"] for r in lock["files"]}:
        raise ValueError("运行时文件集合与锁不一致")
    files = {}
    for row in lock["files"]:
        path = runtime/row["path"]
        if path.is_symlink() or getattr(path.lstat(), "st_file_attributes", 0) & 0x400:
            raise ValueError("运行时含链接")
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != row["sha256"] or len(content) != row["size"]:
            raise ValueError("运行时文件指纹变化")
        if any(part in {"tests", "__pycache__"} for part in Path(row["path"]).parts):
            continue
        files["runtime/"+row["path"]] = content
    temporary_root = ROOT/".local/tmp"
    temporary_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="hsr-wheel-", dir=temporary_root) as temporary:
        if not Path(temporary).resolve().is_relative_to(temporary_root.resolve()):
            raise ValueError("构建临时目录越界")
        subprocess.run([sys.executable, "-m", "hatchling", "build", "-t", "wheel", "-d", temporary], cwd=ROOT, check=True, capture_output=True)
        wheel = next(Path(temporary).glob("*.whl"))
        with zipfile.ZipFile(wheel) as archive:
            for name in archive.namelist():
                if not (name.startswith("companion/") or name.startswith("hsr_ai_companion-")) or any(p in {".local", "__pycache__"} for p in Path(name).parts):
                    raise ValueError("应用 wheel 出现白名单外文件")
                files["runtime/Lib/site-packages/"+name] = archive.read(name)
    for name in ("LICENSE", "licenses/THIRD_PARTY_NOTICES.md", "docs/coverage.md"):
        path = ROOT/name
        if path.exists():
            files[name] = path.read_bytes()
    source_rows = sorted((name, hashlib.sha256(body).hexdigest()) for name, body in files.items() if "/companion/" in name)
    inputs = {"runtime_lock_sha256": hashlib.sha256((ROOT/"manifests/windows-runtime.lock.json").read_bytes()).hexdigest(),
              "dependency_lock_sha256": deps, "business_sha256": hashlib.sha256(canonical(source_rows)).hexdigest(),
              "optional_legacy_backend": "not-bundled; requires separately locked HSR_Nous environment"}
    if update_base:
        from companion.sources.http import public_url
        base = public_url(update_base).rstrip("/")
        inputs["update_sources"] = {"program_source": base+"/windows-x64/release.json", "knowledge_source": base+"/knowledge/release.json"}
    artifact = make_artifact(files, kind="program", version=version, private=private, channel=channel, inputs=inputs)
    name = f"hsr-companion-{version}-windows-x64{'.TEST' if channel == 'test' else ''}.json"
    result = write_release(output, artifact, name, private)
    return result | {"version": version, "channel": channel, "files": len(files), "business_sha256": inputs["business_sha256"]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", choices=["windows-x64"], default="windows-x64")
    parser.add_argument("--version", default=__version__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, default=ROOT/".local/build-inputs/windows-runtime")
    parser.add_argument("--key", type=Path)
    parser.add_argument("--test-signing", action="store_true")
    parser.add_argument("--update-base", help="本次签名绑定的维护者更新根URL；已有玩家配置保持不变")
    args = parser.parse_args()
    if bool(args.key) == args.test_signing:
        parser.error("须选择 --key（DPAPI生产身份）或 --test-signing")
    if args.test_signing:
        private, record = test_key()
        args.output.mkdir(parents=True, exist_ok=True)
        (args.output/"TEST-ONLY-trust.json").write_bytes(canonical({"schema_version": 1, "keys": [record]}))
    else:
        private = unlock(args.key)
    print(json.dumps(build(args.output, runtime=args.runtime, private=private, channel="test" if args.test_signing else "production", version=args.version, update_base=args.update_base), ensure_ascii=False))


if __name__ == "__main__":
    main()
