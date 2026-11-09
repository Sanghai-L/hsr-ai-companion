import hashlib
from pathlib import Path

import pytest

from companion.contracts import canonical
from companion.knowledge.package import build_package
from companion.updates.source import ReleaseSource

SOURCE = Path(__file__).resolve().parents[1] / "fixtures/knowledge/source"


def publish(directory, version="0.1.0", **kwargs):
    directory.mkdir(parents=True, exist_ok=True)
    package = build_package(SOURCE, version=version, **kwargs)
    content = package.encode()
    (directory / "knowledge.json").write_bytes(content)
    (directory / "release.json").write_bytes(canonical({"kind": "knowledge", "version": version,
        "sha256": hashlib.sha256(content).hexdigest(), "size": len(content), "artifact": "knowledge.json"}))
    return package


@pytest.fixture
def release(tmp_path):
    directory = tmp_path / "maintainer"
    publish(directory)
    return directory, ReleaseSource(directory)

