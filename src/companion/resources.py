"""Read the same schemas/migrations from an editable tree or installed wheel."""
from importlib.resources import files
from pathlib import Path


def resource_text(group: str, name: str) -> str:
    packaged = files("companion").joinpath("resources", group, name)
    if packaged.is_file():
        return packaged.read_text(encoding="utf-8")
    root = Path(__file__).resolve().parents[2]
    if group == "schemas" and name == "release.schema.json":
        return (root / "manifests" / name).read_text(encoding="utf-8")
    return (root / group / name).read_text(encoding="utf-8")

