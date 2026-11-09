"""Explicit public-source read; all content and URL records stay in .local."""
import argparse
from pathlib import Path
from common import ROOT, LOCAL, now, digest, write_json
from prepare_runtime import request


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--max-mb", type=int, default=12)
    args = parser.parse_args()
    dest = (ROOT / args.output).resolve()
    if not dest.is_relative_to(LOCAL.resolve()):
        raise ValueError("Downloaded material must remain in private .local")
    if not args.url.startswith("https://"):
        raise ValueError("HTTPS required")
    data = request(args.url, args.max_mb*1024*1024)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    write_json(dest.with_name(dest.name+".origin.json"), {"url": args.url, "at": now(),
        "sha256": digest(dest), "bytes": len(data)})
    print(f"Saved {len(data)} bytes to {dest.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
