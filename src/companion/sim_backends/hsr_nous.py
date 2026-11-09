"""Pinned, offline HSR_Nous core in a separate Python runtime.

The player-facing service never accepts runtime paths, template roots or DSL.
Only the local installation config selects executable code. Knowledge updates
cannot change this config or the packaged integrity manifest.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import subprocess

from companion.contracts import CompanionError, ErrorCode, canonical
from companion.resources import resource_text
from .base import BackendInput

PROTOCOL_VERSION = 1
MAX_INPUT_BYTES = 1024 * 1024
MAX_OUTPUT_BYTES = 16 * 1024 * 1024


def tree_digest(root: Path, *, suffixes=None):
    """Content hash includes names; refuses links and ignores Python caches."""
    digest = hashlib.sha256()
    if not root.is_dir() or root.is_symlink():
        raise CompanionError(ErrorCode.MISSING_DATA, "缺少模拟器锁定目录")
    for path in sorted(root.rglob("*")):
        if "__pycache__" in path.parts:
            continue
        if path.is_symlink() or getattr(path.lstat(), "st_file_attributes", 0) & 0x400:
            raise CompanionError(ErrorCode.INVALID_INPUT, "模拟器目录不能包含链接")
        if not path.is_file() or (suffixes and path.suffix not in suffixes):
            continue
        relative = path.relative_to(root).as_posix().encode("utf-8")
        content = path.read_bytes()
        digest.update(len(relative).to_bytes(4, "big") + relative)
        digest.update(len(content).to_bytes(8, "big") + content)
    return digest.hexdigest()


class HsrNous:
    def __init__(self, *, python, repository, data, generated_templates=None, lock=None):
        self.python = Path(python).resolve()
        self.repository = Path(repository).resolve()
        self.data = Path(data).resolve()
        self.generated_templates = Path(generated_templates).resolve() if generated_templates else None
        self.lock = lock if lock is not None else json.loads(resource_text("manifests", "simulator.lock.json"))

    @classmethod
    def from_context(cls, context):
        # Separate installation file, never writable through knowledge tools.
        from companion.storage import SafeRoot
        if not context.data_dir.is_dir():
            raise CompanionError(ErrorCode.MISSING_DATA, "尚未配置隔离模拟器运行时", details={"fields": ["simulator-runtime.json"]})
        path = SafeRoot(context.data_dir).path("simulator-runtime.json")
        if not path.is_file():
            raise CompanionError(ErrorCode.MISSING_DATA, "尚未配置隔离模拟器运行时", details={"fields": ["simulator-runtime.json"]})
        if path.stat().st_size > 8192:
            raise CompanionError(ErrorCode.INVALID_INPUT, "模拟器本机配置超限")
        try:
            config = json.loads(path.read_bytes())
        except (ValueError, UnicodeError):
            raise CompanionError(ErrorCode.INVALID_INPUT, "模拟器本机配置损坏")
        if (not isinstance(config, dict) or set(config) != {"python", "repository", "data", "generated_templates"}
                or any(not isinstance(v, str) or not Path(v).is_absolute() for v in config.values())):
            raise CompanionError(ErrorCode.INVALID_INPUT, "模拟器配置必须是安装时提供的四个绝对路径")
        return cls(**config)

    def verify(self):
        if not self.python.is_file() or not self.data.is_dir():
            raise CompanionError(ErrorCode.MISSING_DATA, "隔离模拟器解释器或冻结数据不存在")
        checked = []
        roots = {"repository": self.repository, "data": self.data, "generated_templates": self.generated_templates}
        for item in self.lock["content_locks"]:
            root = roots.get(item["root"])
            if root is None:
                raise CompanionError(ErrorCode.MISSING_DATA, "缺少锁定模拟模板目录")
            path = root / item["path"]
            if item["kind"] == "tree":
                actual = tree_digest(path, suffixes=set(item.get("suffixes", [])) or None)
            else:
                if not path.is_file():
                    raise CompanionError(ErrorCode.MISSING_DATA, "锁定模拟器文件不存在")
                actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual != item["sha256"]:
                raise CompanionError(ErrorCode.VERSION_INCOMPATIBLE, "模拟器代码／规则／数据与锁不一致；请重新安装已核验版本",
                                     details={"component": item["path"]})
            checked.append(item["path"])
        adapter = hashlib.sha256()
        for name in ("base.py", "hsr_nous.py", "hsr_nous_worker.py"):
            adapter.update(name.encode() + Path(__file__).with_name(name).read_bytes())
        return {"backend": "hsr-nous", "commit": self.lock["commit"], "patches": self.lock["patches"],
                "adapter_fingerprint": adapter.hexdigest(),
                "content_fingerprint": hashlib.sha256(canonical(self.lock["content_locks"])).hexdigest(),
                "verified_components": checked, "protocol": PROTOCOL_VERSION}

    def capabilities(self):
        return {"backend": "hsr-nous", "commit": self.lock["commit"], "protocol": PROTOCOL_VERSION,
                "modes": ["roll", "expected"], "resume": "immutable_input_rerun_only",
                "game_accuracy_certified": False, "network": "forbidden", "subprocesses": "forbidden_in_core",
                "structured_results": True, "install_check": self.verify()}

    def compile(self, value: BackendInput, *, timeout=30):
        return self._call("compile", value, timeout=timeout)

    def execute(self, value: BackendInput, *, timeout=30):
        return self._call("execute", value, timeout=timeout)

    def _call(self, operation, value, *, timeout):
        if not isinstance(value, BackendInput):
            raise CompanionError(ErrorCode.INVALID_INPUT, "需要结构化模拟输入")
        if not isinstance(value.build, dict) or not isinstance(value.stage, dict) or not isinstance(value.enemy_overrides, dict):
            raise CompanionError(ErrorCode.INVALID_INPUT, "构筑、场景和敌人覆盖必须是结构化对象")
        if (value.mode not in {"roll", "expected"} or type(value.seed) is not int or not 0 <= value.seed < 2**32
                or type(value.initial_sp) is not int or not 0 <= value.initial_sp <= 5
                or isinstance(value.initial_energy_ratio, bool) or not isinstance(value.initial_energy_ratio, (int, float))
                or not math.isfinite(value.initial_energy_ratio) or not 0 <= value.initial_energy_ratio <= 1
                or isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or not 0 < timeout <= 120):
            raise CompanionError(ErrorCode.INVALID_INPUT, "模拟模式、随机种子、初始资源或超时无效")
        metadata = self.verify()
        for actor_id, stats in value.enemy_overrides.items():
            allowed = {"hp", "atk", "def_", "spd", "max_toughness", "effect_res", "resistance"}
            if not isinstance(actor_id, str) or not isinstance(stats, dict) or set(stats) != allowed:
                raise CompanionError(ErrorCode.INVALID_INPUT, "敌人属性覆盖缺少完整数值合同")
            for key, number in stats.items():
                if key == "resistance":
                    if (not isinstance(number, dict) or set(number) - {"physical", "fire", "ice", "thunder", "wind", "quantum", "imaginary"}
                            or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not -1 <= v <= 1 for v in number.values())):
                        raise CompanionError(ErrorCode.INVALID_INPUT, "敌人抗性覆盖无效")
                elif isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number) or number < 0 or (key in {"hp", "spd"} and number == 0):
                    raise CompanionError(ErrorCode.INVALID_INPUT, "敌人属性覆盖数值无效")
        request = {"protocol": PROTOCOL_VERSION, "operation": operation, "input": value.to_dict(),
                   "repository": str(self.repository), "data": str(self.data),
                   "template_roots": [str(self.repository / "data/library"), str(self.generated_templates)]}
        try:
            encoded = canonical(request)
        except (ValueError, TypeError):
            raise CompanionError(ErrorCode.INVALID_INPUT, "模拟输入必须为有限 JSON 数据")
        if len(encoded) > MAX_INPUT_BYTES:
            raise CompanionError(ErrorCode.BUDGET_EXHAUSTED, "模拟输入超过大小限制")
        # -I ignores PYTHONPATH/user site; no account/model credentials are passed.
        env = {key: os.environ[key] for key in ("SYSTEMROOT", "WINDIR", "TEMP", "TMP") if key in os.environ}
        env.update(PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
        runner = Path(__file__).with_name("hsr_nous_worker.py")
        try:
            child = subprocess.run([str(self.python), "-I", "-X", "utf8", str(runner)], input=encoded,
                                   capture_output=True, timeout=timeout, env=env,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        except subprocess.TimeoutExpired:
            raise CompanionError(ErrorCode.BUDGET_EXHAUSTED, "模拟器执行超时，已终止并回收工作进程", retryable=True,
                                 details={"termination": "backend_timeout", "seconds": timeout})
        except OSError:
            raise CompanionError(ErrorCode.MISSING_DATA, "无法启动隔离模拟器解释器")
        if len(child.stdout) > MAX_OUTPUT_BYTES:
            raise CompanionError(ErrorCode.BUDGET_EXHAUSTED, "模拟事件超过输出限制")
        try:
            result = json.loads(child.stdout)
        except (ValueError, UnicodeError):
            raise CompanionError(ErrorCode.INTERNAL_FAILURE, "模拟器未返回结构化结果")
        if result.get("protocol") != PROTOCOL_VERSION:
            raise CompanionError(ErrorCode.VERSION_INCOMPATIBLE, "模拟器协议版本不兼容")
        if child.returncode or result.get("status") != "success":
            code = result.get("error", {}).get("code", "INTERNAL_FAILURE")
            if code not in {member.value for member in ErrorCode}:
                code = "INTERNAL_FAILURE"
            raise CompanionError(ErrorCode(code), "模拟器编译／执行失败",
                                 details={"backend_error": result.get("error", {})})
        return {**result["data"], "backend_version": metadata,
                "enemy_overrides_fingerprint": hashlib.sha256(canonical(value.enemy_overrides)).hexdigest()}
