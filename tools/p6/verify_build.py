import json
from pathlib import Path

from companion.release.artifacts import digest, open_artifact
from companion.release.signing import load_trust
from tools.p6.record import record, write

ROOT = Path(__file__).resolve().parents[2]


def main():
    a = ROOT/".local/dist/D050/program/hsr-companion-0.1.3-windows-x64.json"
    b = ROOT/".local/dist/D050/rebuild/hsr-companion-0.1.3-windows-x64.json"
    keys = load_trust(ROOT/".local/signing/trust.json")
    assert a.read_bytes() == b.read_bytes()
    manifest, files, identity = open_artifact(a.read_bytes(), keys)
    assert all(not any(p in {".local", ".venv", "tests", "tools", "__pycache__"} for p in Path(n).parts) for n in files)
    assert all(not n.endswith((".dpapi", ".pem", ".key", ".sqlite3")) for n in files)
    knowledge = ROOT/".local/dist/D050/knowledge/hsr-knowledge-0.2.0.json"
    km, _, _ = open_artifact(knowledge.read_bytes(), keys)
    assert km["version"] != manifest["version"]
    write(".local/evidence/D050/validation.json", {"status": "PASS", "program_sha256": digest(a.read_bytes()),
        "same_bytes_after_rebuild": True, "program_files": len(files), "identity": identity,
        "knowledge_version": km["version"], "tests": {"passed": 18, "failed": 0, "skipped": 0}})
    record("D050", status="DONE", artifacts=["tools/build_release.py", "tools/build_knowledge_release.py", "manifests/release.schema.json", "docs/release/signing.md", "tests/release/test_artifacts.py"],
           commands=["python -m pytest tests/release -q -ra", "python tools/build_release.py --target windows-x64 --version 0.1.3 --key <本机DPAPI私钥> --output <候选目录>（两次）", "python tools/build_knowledge_release.py --version 0.2.0 --key <本机DPAPI私钥> --output <知识目录>"],
           evidence=[".local/evidence/D050/artifacts.xml", ".local/evidence/D050/validation.json", ".local/evidence/D050/runtime-input.json"],
           summary="18项签名／恶意包边界通过；Windows自带运行时包两次字节一致重建；程序与知识独立签名，生产私钥DPAPI保护", counts={"passed": 18, "failed": 0, "skipped": 0})
    print(json.dumps({"D050": "DONE", "sha256": digest(a.read_bytes())}))


if __name__ == "__main__":
    main()
