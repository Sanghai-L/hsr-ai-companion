"""D006/D007 public documentation and frozen-data collection; no UID queries."""
import json
from pathlib import Path
import urllib.error

from common import ROOT, LOCAL, now, digest, write_json
from prepare_runtime import request


def save(url, path, max_mb=12):
    path = LOCAL / path
    if path.exists() and path.with_name(path.name+".origin.json").exists():
        return path
    data = request(url, max_mb*1024*1024)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    write_json(path.with_name(path.name+".origin.json"), {"url": url, "at": now(),
        "sha256": digest(path), "bytes": len(data)})
    return path


def main():
    errors = []
    for name, url in [
        ("snapshot-release.json", "https://api.github.com/repos/pzc2004/HSR_Nous/releases/tags/data-full-20261016"),
        ("hakushin-manifest.json", "https://static.nanoka.cc/manifest.json"),
        ("enka-wrapper-repo.json", "https://api.github.com/repos/seriaati/enka-py"),
        ("enka-hsr-docs.html", "https://seria.is-a.dev/enka-py/reference/hsr/client/"),
        ("enka-public-sample-documentation.html", "https://seria.is-a.dev/enka-py/profile/"),
    ]:
        try:
            save(url, Path("sources") / name)
            print(json.dumps({"source": name, "saved": True}), flush=True)
        except Exception as exc:
            errors.append({"source": name, "error": str(exc)})
    release_file = LOCAL / "sources/snapshot-release.json"
    if release_file.exists():
        release = json.loads(release_file.read_text(encoding="utf-8"))
        asset = next(a for a in release["assets"] if a["name"] == "data-snapshot.tar.gz")
        if asset["size"] <= 128*1024*1024:
            archive = save(asset["browser_download_url"], Path("sources/data-snapshot.tar.gz"), 128)
            if asset.get("digest") and asset["digest"] != "sha256:"+digest(archive):
                raise ValueError("Data snapshot upstream digest mismatch")
            print(json.dumps({"snapshot_bytes": asset["size"], "downloaded": True}), flush=True)
        else:
            errors.append({"source": "snapshot", "error": "archive exceeds 128 MiB probe budget", "bytes": asset["size"]})
    manifest_file = LOCAL / "sources/hakushin-manifest.json"
    if manifest_file.exists():
        live = json.loads(manifest_file.read_text(encoding="utf-8"))["hsr"]["live"]
        try:
            save(f"https://static.nanoka.cc/hsr/{live}/maze.json", Path("sources/live-maze.json"))
        except Exception as exc:
            errors.append({"source": "live-maze", "error": str(exc)})
    wrapper_file = LOCAL / "sources/enka-wrapper-repo.json"
    if wrapper_file.exists():
        branch = json.loads(wrapper_file.read_text(encoding="utf-8"))["default_branch"]
        tree_file = save(f"https://api.github.com/repos/seriaati/enka-py/git/trees/{branch}?recursive=1", Path("sources/enka-wrapper-tree.json"))
        tree = json.loads(tree_file.read_text(encoding="utf-8"))
        sha = tree["sha"]
        wanted = [x["path"] for x in tree["tree"] if x["type"] == "blob" and (
            x["path"].endswith("hsr/client.py") or x["path"].endswith("hsr/models/player.py") or
            x["path"] in {"enka/clients/hsr.py", "enka/constants/hsr.py", "enka/models/hsr/player.py", "enka/models/hsr/response.py"} or
            x["path"].endswith("profile.md") or x["path"].endswith("test_hsr.py"))]
        for source in wanted:
            save(f"https://raw.githubusercontent.com/seriaati/enka-py/{sha}/{source}", Path("sources/enka-wrapper")/source)
        print(json.dumps({"wrapper_tree_sha": sha, "files": wanted}), flush=True)
    write_json(LOCAL / "evidence/D007/source-collection.json", {"at": now(), "errors": errors})
    print(json.dumps({"errors": errors}), flush=True)


if __name__ == "__main__":
    main()
