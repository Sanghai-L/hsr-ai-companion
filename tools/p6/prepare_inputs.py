"""Fetch one pinned PSF runtime and install hash-locked binary dependencies locally."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import shutil
import urllib.request
import zipfile

from companion.contracts import canonical
from companion.release.artifacts import safe_name

ROOT = Path(__file__).resolve().parents[2]
URL = "https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT/".local/build-inputs/windows-runtime")
    parser.add_argument("--uv", type=Path, help="已有uv程序；不修改全局Python或自动安装开发工具")
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT/".local") or output.exists():
        raise ValueError("输入目录须为 .local 下新的独立目录")
    lock_path = ROOT/"manifests/windows-runtime.lock.json"
    existing = json.loads(lock_path.read_bytes()) if lock_path.exists() else None
    with urllib.request.urlopen(URL, timeout=45) as response:
        content = response.read(20*1024*1024)
    archive_sha = hashlib.sha256(content).hexdigest()
    if existing and archive_sha != existing["archive_sha256"]:
        raise ValueError("已锁定的运行时来源指纹变化")
    output.mkdir(parents=True)
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        for member in archive.infolist():
            name = safe_name(member.filename)
            if member.is_dir():
                continue
            path = output/name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(archive.read(member))
    (output/"python312._pth").write_bytes(b"python312.zip\n.\nLib/site-packages\n")
    uv = args.uv or (ROOT/".local/tools/uv/uv.exe" if (ROOT/".local/tools/uv/uv.exe").is_file() else shutil.which("uv"))
    if not uv:
        raise FileNotFoundError("构建准备需要已有uv；请使用--uv提供本机程序路径")
    command = [str(uv), "pip", "sync", "--python", sys.executable,
               "--target", str(output/"Lib/site-packages"), "--require-hashes", "--only-binary", ":all:",
               str(ROOT/"requirements-runtime.lock")]
    subprocess.run(command, check=True, timeout=180)
    files = [{"path": p.relative_to(output).as_posix(), "sha256": hashlib.sha256(p.read_bytes()).hexdigest(), "size": p.stat().st_size}
             for p in sorted(output.rglob("*")) if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"]
    lock = {"schema_version": 1, "source": URL, "python_version": "3.12.10", "target": "windows-x64",
            "archive_sha256": archive_sha, "dependency_lock_sha256": hashlib.sha256((ROOT/"requirements-runtime.lock").read_bytes()).hexdigest(),
            "files": files}
    lock_path.write_bytes(canonical(lock))
    # Keep the large downloaded archive in the private evidence directory, never in the source tree.
    evidence = ROOT/".local/evidence/D050"
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence/"python-3.12.10-embed-amd64.zip").write_bytes(content)
    (evidence/"runtime-input.json").write_bytes(canonical({"runtime": str(output), "lock": str(lock_path), "source": URL, "archive_sha256": archive_sha}))
    print(json.dumps({"runtime": str(output), "files": len(files), "archive_sha256": archive_sha}))


if __name__ == "__main__":
    main()
