import json
from pathlib import Path
import sqlite3
import sys

import pytest

from companion.accounts import AccountService
from companion.adapters.codex import install_codex
from companion.contracts import CompanionError, canonical
from companion.resources import resource_text
from companion.services.context import Context
from companion.services.registry import Registry
from companion.storage import Store


def test_v1_database_migrates_without_changing_existing_account_and_research(tmp_path):
    database = tmp_path / "personal.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.executescript(resource_text("migrations", "0001_initial.sql"))
        connection.execute("INSERT INTO accounts VALUES('old','original','100000001','ASIA','B','2026-11-01T00:00:00Z')")
        connection.commit()
    assert AccountService(Store(tmp_path, read_only=True)).summary("old")["account"]["label"] == "original"
    migrated = Store(tmp_path)
    assert migrated.require_account("old")["style"] == "B"
    with migrated.connection() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
        assert connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[0] == 0


def test_modified_project_skill_is_preserved_and_install_does_not_partially_write(tmp_path):
    workspace = tmp_path / "project"
    install_codex(workspace, sys.executable, workspace / "player", offline=True)
    skill = workspace / ".agents/skills/research/SKILL.md"
    skill.write_text("player customized research rules", encoding="utf-8")
    config = workspace / ".codex/config.toml"
    before = config.read_bytes()
    with pytest.raises(CompanionError):
        install_codex(workspace, sys.executable, workspace / "different-player", offline=True)
    assert config.read_bytes() == before and skill.read_text() == "player customized research rules"


def test_demo_refuses_existing_nonempty_data(tmp_path):
    import importlib.util
    path = Path(__file__).resolve().parents[2] / "tools/prepare_demo.py"
    spec = importlib.util.spec_from_file_location("prepare_demo_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    directory = tmp_path / "new-demo"
    module.prepare(directory)
    store = Store(directory / "personal", read_only=True)
    assert len(AccountService(store).list()) == 2
    before = (directory / "personal/personal.sqlite3").read_bytes()
    with pytest.raises(ValueError):
        module.prepare(directory)
    assert (directory / "personal/personal.sqlite3").read_bytes() == before


def test_all_new_operations_share_strict_cli_mcp_schemas_and_protect_public_source(tmp_path):
    registry = Registry(Context(tmp_path, offline=True))
    operations = {"knowledge_search", "knowledge_read", "source_fetch", "evidence_register", "evidence_resolve", "account_refresh", "account_patch",
                  "memory_search", "memory_append", "memory_conflict_propose", "memory_revision_apply", "session_context"}
    assert operations <= set(registry.operations)
    for name in operations:
        assert registry.operations[name].schema["additionalProperties"] is False
        assert registry.invoke(name, {"arbitrary": "not supported"}).error["code"] == "INVALID_INPUT"
    assert not any(name in registry.operations for name in ("knowledge_write", "source_execute", "memory_revision_confirm", "research_replace"))
