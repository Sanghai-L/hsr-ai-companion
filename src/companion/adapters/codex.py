"""Preserve user configuration; do not grant project trust or blanket approvals."""
import hashlib
import json
from pathlib import Path
import tomllib

from companion.contracts import CompanionError, ErrorCode, canonical
from companion.resources import resource_text
from companion.storage import SafeRoot
from companion.storage.paths import file_lock

BEGIN, END = "# BEGIN HSR COMPANION", "# END HSR COMPANION"
RULE_BEGIN, RULE_END = "<!-- BEGIN HSR COMPANION -->", "<!-- END HSR COMPANION -->"


def replace_block(text, content, begin=BEGIN, end=END):
    if text.count(begin) != text.count(end) or text.count(begin) > 1:
        raise CompanionError(ErrorCode.CONFLICT, "已有安装管理块损坏")
    block = begin + "\n" + content.rstrip() + "\n" + end
    if begin in text:
        start, finish = text.index(begin), text.index(end) + len(end)
        if finish < start:
            raise CompanionError(ErrorCode.CONFLICT, "已有安装管理块顺序错误")
        return text[:start] + block + text[finish:]
    return text + ("\n" if text and not text.endswith("\n") else "") + block + "\n"


def remove_block(text, begin, end):
    if begin not in text and end not in text:
        return text
    replace_block(text, "", begin, end)  # Validate uniqueness and ordering first.
    start, finish = text.index(begin), text.index(end)+len(end)
    if text[finish:finish+1] == "\n":
        finish += 1
    return text[:start]+text[finish:]


def uninstall_codex(workspace):
    files = SafeRoot(workspace)
    metadata_path = files.path(".hsr-companion/install.json")
    if not metadata_path.is_file():
        raise CompanionError(ErrorCode.CONFLICT, "工作区没有受管的助手接入")
    with file_lock(files, ".hsr-companion/install.lock"):
        metadata = json.loads(metadata_path.read_bytes())
        updates = {}
        for relative, begin, end in ((".codex/config.toml", BEGIN, END), ("AGENTS.md", RULE_BEGIN, RULE_END)):
            path = files.path(relative)
            if path.is_file():
                content = remove_block(path.read_text(encoding="utf-8"), begin, end)
                if relative.endswith(".toml"):
                    tomllib.loads(content)
                updates[relative] = content.encode()
        removed, preserved = [], []
        candidates = {f".agents/skills/{name}/SKILL.md": sha for name, sha in metadata.get("skill_hashes", {}).items()}
        candidates[".hsr-companion/RULES.md"] = metadata.get("rules_sha256")
        candidates.update(metadata.get("managed_hashes", {}))
        for relative in candidates:
            files.path(relative)
        for relative, content in updates.items():
            files.write(relative, content)
        for relative, expected in candidates.items():
            if relative in updates:
                continue
            path = files.path(relative)
            if path.is_file():
                if expected and hashlib.sha256(path.read_bytes()).hexdigest() == expected:
                    path.unlink()
                    removed.append(relative)
                else:
                    preserved.append(relative)
        files.write(".hsr-companion/uninstalled.json", canonical({"removed": removed, "preserved_modified": preserved}))
        metadata_path.unlink()
        return {"workspace": str(files.root), "removed": removed, "preserved_modified": preserved, "user_content_preserved": True}


def install_codex(workspace, python, data_dir, *, offline=False):
    files = SafeRoot(workspace)
    python = Path(python).resolve(strict=True)
    if not python.is_file():
        raise CompanionError(ErrorCode.INVALID_INPUT, "Python 解释器不存在")
    data_dir = Path(data_dir)
    if not data_dir.is_absolute() or data_dir == files.root:
        raise CompanionError(ErrorCode.INVALID_INPUT, "数据目录须为独立绝对路径")
    files.mkdir(".hsr-companion")
    with file_lock(files, ".hsr-companion/install.lock"):
        config_path = files.path(".codex/config.toml")
        old = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
        try:
            parsed = tomllib.loads(old)
        except ValueError as error:
            raise CompanionError(ErrorCode.CONFLICT, "已有 Codex 配置无效，未覆盖") from error
        if "hsr_companion" in parsed.get("mcp_servers", {}) and BEGIN not in old:
            raise CompanionError(ErrorCode.CONFLICT, "已有同名 MCP 配置，未覆盖")
        args = ["-m", "companion", "--data-dir", str(data_dir), *(["--offline"] if offline else []), "mcp"]
        managed_root = python.parents[3] if len(python.parents) > 3 else None
        if managed_root and (managed_root/"install-state.json").is_file():
            args = ["-I", "-m", "companion.install.launcher", "--root", str(managed_root), "--", *(["--offline"] if offline else []), "mcp"]
        template = resource_text("adapters", "codex/config.toml.template")
        for key, value in {"python": str(python), "args": args, "workspace": str(files.root)}.items():
            template = template.replace("{{" + key + "}}", json.dumps(value, ensure_ascii=False))
        config = replace_block(old, template)
        try:
            tomllib.loads(config)
        except ValueError as error:
            raise CompanionError(ErrorCode.CONFLICT, "合并后的 Codex 配置无效，未写入") from error
        agents_path = files.path("AGENTS.md")
        agents = agents_path.read_text(encoding="utf-8") if agents_path.exists() else ""
        rules = resource_text("adapters", "common/RULES.md").encode("utf-8")
        agents = replace_block(agents, "以下规则由 adapters/common/RULES.md 生成，内容已直接载入，无需额外 shell 读取。\n\n" + rules.decode("utf-8"), RULE_BEGIN, RULE_END)
        overrides = ["mcp_servers.hsr_companion.command=" + json.dumps(str(python), ensure_ascii=False),
                     "mcp_servers.hsr_companion.args=" + json.dumps(args, ensure_ascii=False),
                     "mcp_servers.hsr_companion.cwd=" + json.dumps(str(files.root), ensure_ascii=False),
                     "mcp_servers.hsr_companion.startup_timeout_sec=15",
                     "mcp_servers.hsr_companion.tool_timeout_sec=30"]
        launch_args = ["--cd", str(files.root)]
        for override in overrides:
            launch_args += ["-c", override]
        quote_ps = lambda value: "'" + value.replace("'", "''") + "'"
        launcher = ("# Project-only compatibility entry; preserves user/global configuration.\n"
                    "$hsrCompanionArgs = @(\n  " + ",\n  ".join(quote_ps(value) for value in launch_args) +
                    "\n)\n& codex @hsrCompanionArgs @args\nexit $LASTEXITCODE\n")
        rules_path = files.path(".hsr-companion/RULES.md")
        metadata_path = files.path(".hsr-companion/install.json")
        previous = json.loads(metadata_path.read_bytes()) if metadata_path.exists() else {}
        if rules_path.exists() and hashlib.sha256(rules_path.read_bytes()).hexdigest() != previous.get("rules_sha256"):
            raise CompanionError(ErrorCode.CONFLICT, "已有规则文件被修改，未覆盖")
        outputs = {".codex/config.toml": config.encode("utf-8"), "AGENTS.md": agents.encode("utf-8"),
                   ".hsr-companion/mcp-overrides.json": canonical(overrides),
                   ".hsr-companion/打开助手.ps1": b"\xef\xbb\xbf" + launcher.encode("utf-8"),
                   ".hsr-companion/RULES.md": rules, ".hsr-companion/install.json": canonical({
                       "host": "codex", "rules_sha256": hashlib.sha256(rules).hexdigest(),
                       "python": str(python), "data_dir": str(data_dir), "offline": offline})}
        # Project skills belong to executable installation, never knowledge content updates.
        skills_hashes = {}
        for name in ("research", "discussion", "memory"):
            relative = f".agents/skills/{name}/SKILL.md"
            content = resource_text("skills", f"{name}/SKILL.md").encode("utf-8")
            destination = files.path(relative)
            prior_hash = previous.get("skill_hashes", {}).get(name)
            if destination.exists() and hashlib.sha256(destination.read_bytes()).hexdigest() not in {prior_hash, hashlib.sha256(content).hexdigest()}:
                raise CompanionError(ErrorCode.CONFLICT, "已有同名项目技能被修改，未覆盖")
            skills_hashes[name] = hashlib.sha256(content).hexdigest()
            outputs[relative] = content
        metadata = json.loads(outputs[".hsr-companion/install.json"])
        metadata["skill_hashes"] = skills_hashes
        metadata["managed_hashes"] = {relative: hashlib.sha256(content).hexdigest() for relative, content in outputs.items() if relative != ".hsr-companion/install.json"}
        outputs[".hsr-companion/install.json"] = canonical(metadata)
        # Check every destination before the first write.
        for relative in outputs:
            files.path(relative)
        changed = []
        for relative, content in outputs.items():
            destination = files.path(relative)
            if not destination.exists() or destination.read_bytes() != content:
                files.write(relative, content)
                changed.append(relative)
        if managed_root and (managed_root/"install-state.json").is_file():
            managed_files = SafeRoot(managed_root)
            with file_lock(managed_files, "install.lock"):
                path = managed_files.path("workspaces.json")
                workspaces = json.loads(path.read_bytes()) if path.is_file() else []
                managed_files.write("workspaces.json", canonical(sorted(set([*workspaces, str(files.root)]))))
        return {"host": "codex", "changed": changed, "workspace": str(files.root), "trust_granted": False}

