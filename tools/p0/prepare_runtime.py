"""Prepare only a project-local uv and locked simulator core dependencies."""
import hashlib
import json
import os
from pathlib import Path
import sys
import urllib.request
import zipfile

from common import ROOT, LOCAL, now, write_json, command


def request(url, limit):
    req = urllib.request.Request(url, headers={"User-Agent": "HSRCompanion-P0/0.1"})
    with urllib.request.urlopen(req, timeout=60) as response:
        if int(response.headers.get("Content-Length", "0")) > limit:
            raise ValueError("Download exceeds explicit local probe budget")
        content = response.read(limit+1)
    if len(content) > limit:
        raise ValueError("Download exceeds explicit local probe budget")
    return content


def main():
    uv_path = LOCAL / "tools/uv/uv.exe"
    pin_path = ROOT / "manifests/probe-tools.lock.json"
    pin = json.loads(pin_path.read_text(encoding="utf-8")).get("uv") if pin_path.exists() else None
    if not uv_path.exists():
        release_url = ("https://api.github.com/repos/astral-sh/uv/releases/tags/"+pin["release"]
                       if pin else "https://api.github.com/repos/astral-sh/uv/releases/latest")
        release = json.loads(request(release_url, 2*1024*1024))
        asset = next(x for x in release["assets"] if x["name"] == "uv-x86_64-pc-windows-msvc.zip")
        content = request(asset["browser_download_url"], 40*1024*1024)
        sha = hashlib.sha256(content).hexdigest()
        if pin and sha != pin["archive_sha256"]:
            raise ValueError("Pinned uv archive hash mismatch")
        upstream_digest = asset.get("digest")
        if upstream_digest and upstream_digest != "sha256:"+sha:
            raise ValueError("Upstream uv digest mismatch")
        archive = LOCAL / "tools/uv/uv.zip"
        archive.parent.mkdir(parents=True, exist_ok=True)
        archive.write_bytes(content)
        with zipfile.ZipFile(archive) as z:
            names = [n for n in z.namelist() if Path(n).name == "uv.exe"]
            if len(names) != 1:
                raise ValueError("Expected one uv executable")
            uv_path.write_bytes(z.read(names[0]))
        write_json(LOCAL / "tools/uv/origin.json", {"release": release["tag_name"],
            "url": asset["browser_download_url"], "archive_sha256": sha,
            "upstream_digest": upstream_digest, "executable_sha256": hashlib.sha256(uv_path.read_bytes()).hexdigest(), "at": now()})
    if pin and hashlib.sha256(uv_path.read_bytes()).hexdigest() != pin["executable_sha256"]:
        raise ValueError("Pinned uv executable hash mismatch")
    python = LOCAL / "probes/hsr-nous/中文 空格验证/Scripts/python.exe"
    repo = LOCAL / "upstream/hsr-nous/repo"
    env = os.environ.copy()
    env.update(UV_CACHE_DIR=str(LOCAL / "cache/uv"), UV_NO_PROGRESS="1", UV_PYTHON_DOWNLOADS="never")
    commands = [
        ("uv-version", [uv_path, "--version"]),
        ("resolve-core-lock", [uv_path, "pip", "compile", "tools/p0/simulator-requirements.in", "--python", python,
                               "--generate-hashes", "--output-file", "tools/p0/simulator-requirements.lock"]),
        ("install-core-lock", [uv_path, "pip", "sync", "--python", python, "tools/p0/simulator-requirements.lock", "--require-hashes"]),
        ("install-upstream-no-deps", [uv_path, "pip", "install", "--python", python, "--no-deps", "--no-build-isolation", "-e", repo]),
        ("installed-versions", [uv_path, "pip", "freeze", "--python", python]),
    ]
    for name, args in commands:
        # Do not re-resolve an already frozen lock on a normal rerun.
        if name == "resolve-core-lock" and (ROOT / "tools/p0/simulator-requirements.lock").exists():
            continue
        result = command(args, task="D008", name=name, timeout=180, env=env)
        print(json.dumps({"step": name, "exit_code": result["exit_code"]}), flush=True)
        if result["exit_code"] != 0:
            raise RuntimeError(result["stderr"])


if __name__ == "__main__":
    main()
