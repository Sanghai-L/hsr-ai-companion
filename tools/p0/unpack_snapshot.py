"""D007: bounded extraction of regular JSON files; reject links and escapes."""
import json
from pathlib import Path
import tarfile

from common import ROOT, LOCAL, digest, now, write_json, update_task


def main():
    update_task("D007", "IN_PROGRESS", summary="已取得固定日期快照，开始核对正式服版本、期数与字段",
                next_step="冻结可复放场景", level="公开来源实读")
    target = (LOCAL / "data-snapshot").resolve()
    target.mkdir(parents=True, exist_ok=True)
    files = []
    with tarfile.open(LOCAL / "sources/data-snapshot.tar.gz", mode="r:gz") as archive:
        members = archive.getmembers()
        if sum(m.size for m in members) > 128*1024*1024:
            raise ValueError("Unpacked data exceeds limit")
        for member in members:
            if member.isdir():
                continue
            path = (target / member.name).resolve()
            if not member.isfile() or not path.is_relative_to(target) or path.suffix != ".json":
                raise ValueError("Only regular contained JSON files may be extracted: " + member.name)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(archive.extractfile(member).read())
            files.append({"path": path.relative_to(target).as_posix(), "sha256": digest(path)})
    write_json(LOCAL / "evidence/D007/snapshot-files.json", {"at": now(), "archive_sha256": digest(LOCAL/"sources/data-snapshot.tar.gz"), "files": files})
    live = json.loads((LOCAL/"sources/hakushin-manifest.json").read_text(encoding="utf-8"))["hsr"]["live"]
    print(json.dumps({"files": len(files), "source_reports_live_version": live}, ensure_ascii=False))
    for name in ("stages/hakushin/_snapshot_meta.json", "stages/hakushin/_update_manifest.json", "stages/hakushin/maze.json", "stages/buhflipexplode/fh-versions.json"):
        data = json.loads((target/name).read_text(encoding="utf-8"))
        print(name, json.dumps(data, ensure_ascii=False)[:2400])


if __name__ == "__main__":
    main()
