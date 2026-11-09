import json

import pytest

from companion.install import Installer
from companion.release.artifacts import make_artifact
from companion.release.signing import test_key as new_key


def test_signed_initial_sources_merge_preserve_user_config_and_roll_back_on_failure(tmp_path):
    private, public = new_key()
    data = tmp_path/"player"
    data.mkdir()
    original = b'{"check_interval":3600}'
    (data/"config.json").write_bytes(original)
    urls = {"program_source": "https://example.com/install/windows-x64/release.json", "knowledge_source": "https://example.com/install/knowledge/release.json"}
    content = make_artifact({"runtime/python.exe": b"synthetic"}, kind="program", version="0.1.3", private=private, inputs={"update_sources": urls})
    manager = Installer(tmp_path/"app", data, trusted_keys=[public], allow_test=True, health_check=lambda *args:{"status":"PASS","version":"0.1.3"})
    manager.checkpoint = lambda phase: (_ for _ in ()).throw(OSError("injected power loss")) if phase == "migrated" else None
    with pytest.raises(OSError):
        manager.install(content)
    assert (data/"config.json").read_bytes() == original
    manager.checkpoint = lambda phase: None
    manager.install(content)
    assert json.loads((data/"config.json").read_bytes()) == {"check_interval":3600, **urls}
