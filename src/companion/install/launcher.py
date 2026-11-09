"""Shared activity lease for a complete CLI/MCP process lifetime."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

from companion.cli import main as companion_main
from companion.storage import SafeRoot
from companion.storage.paths import file_lock


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    args, rest = parser.parse_known_args()
    if rest[:1] == ["--"]:
        rest = rest[1:]
    files = SafeRoot(args.root)
    with file_lock(files, "activity.lock", shared=True):
        state = json.loads(files.path("install-state.json").read_bytes())
        current_python = files.path("versions/"+state["current"]["digest"]+"/runtime/python.exe")
        if Path(sys.executable).resolve() != current_python.resolve():
            return subprocess.call([str(current_python), "-I", "-m", "companion.install.launcher", "--root", str(files.root), "--", *rest])
        import os
        os.environ["HSR_COMPANION_INSTALL_ROOT"] = str(files.root)
        return companion_main(["--data-dir", state["data_dir"], *rest])


if __name__ == "__main__":
    sys.exit(main())
