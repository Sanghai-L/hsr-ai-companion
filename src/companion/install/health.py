"""Candidate-only migration/self-test entry. Never opens the live player directory."""
import argparse
import json
from pathlib import Path

from companion import __version__
from companion.calculators import damage
from companion.services.context import Context


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, required=True)
    args = parser.parse_args()
    context = Context(args.data_dir, offline=True)
    if (args.data_dir/"personal/personal.sqlite3").is_file():
        context.store  # Apply packaged migrations against the private candidate copy.
        context.inspect()
    from companion.services.registry import Registry
    assert Registry(context).invoke("doctor", {}).status == "success"
    print(json.dumps({"status": "PASS", "version": __version__, "live_player_access": False}))


if __name__ == "__main__":
    main()
