"""D003: read and pin public candidates; do not execute downloaded code."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import urllib.error
import urllib.request

from common import ROOT, LOCAL, command, now, write_json

CANDIDATES = [
    ("hsr-nous", "pzc2004/HSR_Nous", "MIT", "simulation-core", ["README.md", "LICENSE", "pyproject.toml", "src/hsr_nous/sim/README.md", "tests/README.md", "docs/engine_design.md"]),
    ("hsr-knowledge-base", "ganmayou2333/hsr-knowledge-base", "AGPL-3.0", "reference-only", ["README.md", "LICENSE", "NOTICE.md"]),
    ("srsim", "ZSim-Dev/SRSim", "GPL-3.0", "alternative-research-only", ["README.md", "LICENSE", "pyproject.toml"]),
    ("hsr-mechanic-sim", "louis0617/hsr-mechanic-sim", "UNRESOLVED", "exclude-from-distribution", ["README.md", "LICENSE", "package.json"]),
    ("starrailres", "Mar-7th/StarRailRes", "AGPL-3.0", "local-data-reference-only", ["README.md", "LICENSE"]),
    ("enka-api-docs", "EnkaNetwork/API-docs", "UNRESOLVED", "api-documentation-only", ["README.md", "api.md", "LICENSE"]),
    ("markdown-kb-mcp", "ganmayou2333/markdown-kb-mcp", "MIT", "optional-search-candidate-not-installed", ["README.md", "LICENSE", "pyproject.toml", "package.json"]),
    ("dsh", "deepseek-ai/deepseek-harness", "MIT", "host-documentation-only", ["README.md", "LICENSE", "package.json", "packages/mcp/mcp-client/README.md", "docs/subsystems/web.md"]),
]


def fetch(url, path):
    request = urllib.request.Request(url, headers={"User-Agent": "HSRCompanion-P0/0.1 (local feasibility probe)"})
    try:
        with urllib.request.urlopen(request, timeout=40) as response:
            data = response.read(12 * 1024 * 1024 + 1)
        if len(data) > 12 * 1024 * 1024:
            raise ValueError("Source file exceeds probe budget")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return {"path": path.relative_to(ROOT).as_posix(), "url": url,
                "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data), "status": 200}
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise
        return {"url": url, "status": 404}


def main():
    lock_path = ROOT / "manifests/upstreams.lock.json"
    previous = json.loads(lock_path.read_text(encoding="utf-8")) if lock_path.exists() else {}
    pinned = {entry["id"]: entry for entry in previous.get("upstreams", [])}
    manifest = {"schema_version": 1, "recorded_at": now(), "upstreams": []}
    if "primary_core_audit" in previous:
        manifest["primary_core_audit"] = previous["primary_core_audit"]
    for key, repo, license_hint, scope, paths in CANDIDATES:
        # Preserve a pin once selected. A refresh is a separate, deliberate operation.
        pin_path = LOCAL / "upstream" / key / "pin.json"
        if key in pinned:
            sha = pinned[key]["commit"]
            branch = pinned[key]["default_branch_observed"]
            if pin_path.exists() and json.loads(pin_path.read_text(encoding="utf-8"))["commit"] != sha:
                raise ValueError("Private pin disagrees with shared lock; explicit review required")
            write_json(pin_path, {"commit": sha, "default_branch": branch, "at": now()})
        elif pin_path.exists():
            pin = json.loads(pin_path.read_text(encoding="utf-8"))
            sha, branch = pin["commit"], pin["default_branch"]
        else:
            result = command(["git", "ls-remote", "--symref", f"https://github.com/{repo}.git", "HEAD"],
                             task="D003", name=key+"-remote", timeout=90)
            if result["exit_code"] != 0:
                raise RuntimeError(result["stderr"])
            sha = re.search(r"^([a-f0-9]{40})\s+HEAD$", result["stdout"], re.M).group(1)
            branch = re.search(r"ref: refs/heads/(\S+)\s+HEAD", result["stdout"]).group(1)
            write_json(pin_path, {"commit": sha, "default_branch": branch, "at": now()})
        entry = {**pinned.get(key, {}), "id": key, "repository": f"https://github.com/{repo}", "commit": sha,
                 "default_branch_observed": branch, "license_observed": license_hint,
                 "scope": scope, "redistribution_approved": False, "files": []}
        for source in paths:
            dest = LOCAL / "upstream" / key / "documents" / source
            if dest.exists():
                data = dest.read_bytes()
                record = {"path": dest.relative_to(ROOT).as_posix(),
                          "url": f"https://raw.githubusercontent.com/{repo}/{sha}/{source}",
                          "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data), "status": 200}
            else:
                record = fetch(f"https://raw.githubusercontent.com/{repo}/{sha}/{source}", dest)
            previous_file = next((f for f in pinned.get(key, {}).get("files", []) if f["url"] == record["url"]), None)
            if previous_file and (previous_file["status"] != record["status"] or
                                  (record["status"] == 200 and previous_file["sha256"] != record["sha256"])):
                raise ValueError("Source content disagrees with frozen lock: " + record["url"])
            entry["files"].append(record)
        manifest["upstreams"].append(entry)
        write_json(ROOT / "manifests/upstreams.lock.json", manifest)
        print(json.dumps({"upstream": key, "commit": sha, "files": len(entry["files"])}, ensure_ascii=False), flush=True)
    # Only the primary backend is checked out for execution. No package postinstall.
    primary = manifest["upstreams"][0]
    checkout = LOCAL / "upstream/hsr-nous/repo"
    if not (checkout / ".git").exists():
        if checkout.exists() and any(checkout.iterdir()):
            raise ValueError("Checkout directory is nonempty without Git metadata; refusing to overwrite")
        checkout.mkdir(parents=True, exist_ok=True)
        for name, args in [
            ("init", ["git", "init"]),
            ("origin", ["git", "remote", "add", "origin", primary["repository"]+".git"]),
            ("fetch-pinned", ["git", "fetch", "--depth", "1", "origin", primary["commit"]]),
            ("detach-pinned", ["git", "checkout", "--detach", primary["commit"]]),
        ]:
            result=command(args,task="D003",name="hsr-nous-"+name,cwd=checkout,timeout=180)
            if result["exit_code"] != 0:
                raise RuntimeError(result["stderr"])
    actual = command(["git", "rev-parse", "HEAD"], task="D003", name="hsr-nous-checked-sha", cwd=checkout)
    if actual["stdout"].strip() != primary["commit"]:
        raise RuntimeError("Clone HEAD changed; refusing to silently replace selected commit")
    for repair in primary.get("local_patches", []):
        patch = (ROOT / repair["path"]).resolve()
        if not patch.is_relative_to((ROOT/"patches").resolve()) or hashlib.sha256(patch.read_bytes()).hexdigest() != repair["sha256"]:
            raise ValueError("Local repair path/hash mismatch")
        already=command(["git","apply","--reverse","--check",patch],task="D003",name="patch-already-applied",cwd=checkout)
        if already["exit_code"] != 0:
            checked=command(["git","apply","--check",patch],task="D003",name="patch-apply-check",cwd=checkout)
            if checked["exit_code"] != 0:
                raise RuntimeError("Pinned repair cannot apply cleanly; refusing to alter checkout")
            applied=command(["git","apply",patch],task="D003",name="patch-apply",cwd=checkout)
            if applied["exit_code"] != 0:
                raise RuntimeError(applied["stderr"])
    print("Pinned HSR_Nous checkout verified; no upstream code executed.")


if __name__ == "__main__":
    main()
