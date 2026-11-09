"""Project-scoped local installation only; no download, trust change or global edits."""
import argparse
import json
from pathlib import Path
import sys

from companion.adapters.codex import install_codex


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    print(json.dumps(install_codex(Path(args.workspace), args.python, Path(args.data_dir), offline=args.offline), ensure_ascii=False))


if __name__ == "__main__":
    main()

