"""Reproduce the versioned representative Alpha case through the public registry."""
import argparse
import hashlib
import json
from pathlib import Path

from companion.contracts import canonical
from companion.services.context import Context
from companion.services.registry import Registry


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, default=Path("benchmarks/catalog.json"))
    parser.add_argument("--case", default="alpha-moc")
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    catalog = args.catalog.resolve()
    root = catalog.parent.parent
    selected = next(row for row in json.loads(catalog.read_bytes())["cases"] if row["id"] == args.case)["representative"]
    path = (root / selected["path"]).resolve()
    if not path.is_relative_to(root):
        raise ValueError("catalog reference escapes project")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != selected["sha256"]:
        raise ValueError("representative snapshot changed")
    args.output.mkdir(parents=True, exist_ok=False)
    request = json.loads(raw)
    registry = Registry(Context(args.data_dir, offline=True))
    result = registry.invoke("simulation_compare", {"request": request})
    (args.output / "input.json").write_bytes(canonical({"request": request}))
    (args.output / "result.json").write_bytes(canonical(result.to_dict()))
    repeated = registry.invoke("simulation_compare", {"request": request})
    if repeated.data != result.data:
        raise RuntimeError("same input changed result")
    print(json.dumps({"status": result.status, "label": result.data["label"], "ranking": result.data["ranking"],
                      "same_result": True, "output": str(args.output), "uid_queries": 0}, ensure_ascii=False))
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
