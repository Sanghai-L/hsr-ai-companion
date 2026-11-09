"""Build independently versioned, authenticated, content-only knowledge releases."""
import argparse
import json
from pathlib import Path

from companion.knowledge.package import build_package
from companion.release.artifacts import make_artifact, write_release
from companion.release.private_key import unlock

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=ROOT/"knowledge")
    parser.add_argument("--version", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--key", type=Path, required=True)
    args = parser.parse_args()
    private = unlock(args.key)
    package = build_package(args.source, version=args.version)
    content = make_artifact({"package.json": package.encode()}, kind="knowledge", version=args.version, private=private, channel="production")
    print(json.dumps(write_release(args.output, content, f"hsr-knowledge-{args.version}.json", private)))


if __name__ == "__main__":
    main()
