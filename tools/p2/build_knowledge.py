"""Build the packaged starter knowledge from reviewed maintainer content."""
from pathlib import Path
from companion.knowledge.package import build_package

ROOT = Path(__file__).resolve().parents[2]


def main():
    package = build_package(ROOT / "knowledge", version="0.2.0")
    path = ROOT / "src/companion/resources/knowledge/bundle.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(package.encode())
    print(package.fingerprint, len(package.manifest["entries"]))


if __name__ == "__main__":
    main()
