import hashlib
import sys
import tomllib

import pytest

from companion.adapters.codex import install_codex
from companion.contracts import CompanionError


def test_uninstall_removes_managed_configuration_and_preserves_user_content(tmp_path):
    from companion.adapters.codex import uninstall_codex
    workspace = tmp_path/"project"
    (workspace/".codex").mkdir(parents=True)
    (workspace/".codex/config.toml").write_text('model = "user-model"\n', encoding="utf-8")
    (workspace/"AGENTS.md").write_text("玩家自己的规则\n", encoding="utf-8")
    install_codex(workspace, sys.executable, workspace/"player", offline=True)
    skill = workspace/".agents/skills/research/SKILL.md"
    skill.write_text("玩家修改后的技能", encoding="utf-8")
    result = uninstall_codex(workspace)
    assert (workspace/".codex/config.toml").read_text(encoding="utf-8") == 'model = "user-model"\n'
    assert (workspace/"AGENTS.md").read_text(encoding="utf-8") == "玩家自己的规则\n"
    assert skill.read_text(encoding="utf-8") == "玩家修改后的技能"
    assert ".agents/skills/research/SKILL.md" in result["preserved_modified"]


def test_absolute_paths_spaces_idempotence_and_user_config(tmp_path):
    workspace = tmp_path / "中文 空格项目"
    workspace.mkdir()
    (workspace / ".codex").mkdir()
    original = '# 玩家自己的配置\n[mcp_servers.other]\ncommand = "existing"\n'
    (workspace / ".codex/config.toml").write_text(original, encoding="utf-8")
    (workspace / "AGENTS.md").write_text("玩家规则\n", encoding="utf-8")
    first = install_codex(workspace, sys.executable, workspace / "私有 资料", offline=True)
    assert first["changed"] and first["trust_granted"] is False
    second = install_codex(workspace, sys.executable, workspace / "私有 资料", offline=True)
    assert second["changed"] == []
    config = (workspace / ".codex/config.toml").read_text(encoding="utf-8")
    assert config.startswith(original) and config.count("[mcp_servers.hsr_companion]") == 1
    parsed = tomllib.loads(config)["mcp_servers"]["hsr_companion"]
    assert parsed["args"][-2:] == ["--offline", "mcp"]
    assert "approval_mode" not in config and "trust_level" not in config
    assert (workspace / "AGENTS.md").read_text(encoding="utf-8").startswith("玩家规则\n")


def test_unmanaged_configuration_or_modified_rules_are_preserved(tmp_path):
    workspace = tmp_path / "project"
    install_codex(workspace, sys.executable, workspace / "private")
    rules = workspace / ".hsr-companion/RULES.md"
    rules.write_text("玩家手工修改", encoding="utf-8")
    config = workspace / ".codex/config.toml"
    before = hashlib.sha256(config.read_bytes()).hexdigest()
    with pytest.raises(CompanionError):
        install_codex(workspace, sys.executable, workspace / "private")
    assert hashlib.sha256(config.read_bytes()).hexdigest() == before
    assert rules.read_text(encoding="utf-8") == "玩家手工修改"

