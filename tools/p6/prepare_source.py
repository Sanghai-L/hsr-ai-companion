"""Prepare a reviewable outbound tree; never upload or read arbitrary private directories."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

from companion.contracts import canonical
from companion.release.artifacts import open_artifact
from companion.release.signing import load_trust
from companion.storage import SafeRoot

ROOT = Path(__file__).resolve().parents[2]
DIRECTORIES = ["src", "schemas", "migrations", "skills", "knowledge", "licenses", "tests", "evals", "benchmarks", "tools"]
FILES = [".gitignore", ".gitattributes", "pyproject.toml", "requirements.in", "requirements.lock", "requirements-runtime.in", "requirements-runtime.lock",
         "README.md", "INSTALL_AGENT.md", "CONTRIBUTING.md", "LICENSE"]
DOCS = ["docs/coverage.md", "docs/privacy.md", "docs/security-boundaries.md", "docs/troubleshooting.md", "docs/contracts", "docs/release", "docs/maintenance",
        "docs/gates/P6-release-candidate.md",
        "docs/gates/P6-release-candidate.json", "docs/gates/maintenance-ready.md", "docs/gates/maintenance-ready.json",
        "docs/validation/agent-evals.md", "docs/validation/windows-install-matrix.md", "docs/validation/performance.md", "docs/modes", ".github/ISSUE_TEMPLATE"]
MANIFESTS = ["analysis-mechanics.json", "build-catalog.json", "coverage.json", "release.schema.json", "simulator.lock.json", "windows-runtime.lock.json"]


def prepare(output, media, knowledge):
    output = output.resolve()
    if not output.is_relative_to((ROOT/".local/outgoing").resolve()) or output.exists():
        raise ValueError("对外候选树须为 .local/outgoing 下新目录")
    output.mkdir(parents=True)
    source_root = SafeRoot(ROOT)
    SafeRoot(output)
    candidates = []
    for name in DIRECTORIES+FILES+DOCS+["adapters/common", "adapters/codex"]+["manifests/"+m for m in MANIFESTS]:
        path = ROOT/name
        if not path.exists():
            raise FileNotFoundError(name)
        candidates.extend([path] if path.is_file() else path.rglob("*"))
    for source in sorted(set(candidates)):
        source_root.path(source.relative_to(ROOT).as_posix())
        if not source.is_file() or "__pycache__" in source.parts or source.suffix == ".pyc":
            continue
        relative = source.relative_to(ROOT)
        if any(part in {".local", ".venv", ".git", ".codex"} for part in relative.parts) or source.is_symlink():
            raise ValueError("源文件不在对外白名单中")
        content = source.read_bytes()
        normalized = content.replace(b"\\\\", b"\\")
        home = str(Path.home()).encode("utf-8")
        if any(marker in normalized for marker in (home, home.replace(b"\\", b"/"), b"xwechat_"+b"files", b"BEGIN "+b"PRIVATE KEY", b"BEGIN OPENSSH "+b"PRIVATE KEY")):
            raise ValueError("对外文件包含本机身份路径或私钥标记："+str(relative))
        destination = output/relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
    checksums = json.loads((media/"checksums.json").read_bytes())
    artifact_name = checksums["program_artifact"]
    for folder, source in (("install/windows-x64", media), ("install/knowledge", knowledge)):
        for path in source.iterdir():
            if not path.is_file() or path.name not in {"Install-HSR.ps1", "bootstrap.zip", artifact_name, "trust.json", "checksums.json", "release.json", "hsr-knowledge-0.2.0.json"}:
                continue
            destination = output/folder/path.name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(path.read_bytes())
    keys = load_trust(media/"trust.json")
    manifest, payload, _ = open_artifact((media/artifact_name).read_bytes(), keys)
    for source in (output/"src/companion").rglob("*.py"):
        package_path = "runtime/Lib/site-packages/companion/"+source.relative_to(output/"src/companion").as_posix()
        if payload.get(package_path) != source.read_bytes():
            raise ValueError("源代码与签名候选不一致："+str(source))
    listing = [{"path": p.relative_to(output).as_posix(), "size": p.stat().st_size, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
               for p in sorted(output.rglob("*")) if p.is_file()]
    report = {"state": "REVIEWABLE_NOT_UPLOADED", "repository": "Sanghai-L/hsr-ai-companion", "visibility_observed": "public", "program_version": manifest["version"],
              "files": listing, "file_count": len(listing), "bytes": sum(r["size"] for r in listing),
              "excluded": [".local", "private evidence", "personal accounts/research", "development venv", "signing private key", "requirements origin documents"],
              "tree_sha256": hashlib.sha256(canonical(listing)).hexdigest()}
    report_path = output.parent/(output.name+"-outbound-review.json")
    report_path.write_bytes(canonical(report))
    print(json.dumps({"output": str(output), "file_count": len(listing), "bytes": report["bytes"], "tree_sha256": report["tree_sha256"], "review": str(report_path)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--media", type=Path, required=True)
    parser.add_argument("--knowledge", type=Path, required=True)
    args = parser.parse_args()
    prepare(args.output, args.media, args.knowledge)
