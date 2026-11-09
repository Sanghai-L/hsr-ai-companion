"""CLI uses the exact operation functions exposed by the MCP server."""
import argparse
import json
import sqlite3
from pathlib import Path
import sys

from companion import __version__
from companion.contracts import CompanionError, ErrorCode, ToolResult, canonical
from companion.services.context import Context
from companion.services.registry import Registry


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="companion", description="星穹铁道本地助手")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--data-dir", default=".local/companion", help="本次调用使用的本地私有目录")
    parser.add_argument("--offline", action="store_true", help="本次调用及子任务禁止外网")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("doctor", "status", "capabilities"):
        child = sub.add_parser(name)
        child.add_argument("--json", action="store_true")
    call = sub.add_parser("call")
    call.add_argument("operation")
    call.add_argument("--input", required=True, help="JSON 对象文件；- 表示 stdin")
    call.add_argument("--json", action="store_true")
    sub.add_parser("mcp", help="启动 stdio MCP 服务；EOF 后退出")
    configure = sub.add_parser("configure-codex", help="把受管安装接入指定项目，保留已有配置")
    configure.add_argument("--root", type=Path, required=True)
    configure.add_argument("--workspace", type=Path, required=True)
    for action in ("install-program", "rollback-program", "uninstall-program", "recover-program"):
        installer = sub.add_parser(action, help="管理项目内程序版本，保留独立的个人目录")
        installer.add_argument("--root", type=Path, required=True)
        installer.add_argument("--trust", type=Path, required=True)
        if action == "install-program":
            installer.add_argument("--package", type=Path, required=True)
            installer.add_argument("--allow-test", action="store_true")
        if action == "uninstall-program":
            installer.add_argument("--purge-data", action="store_true", help="独立选择：把个人目录移到隔离名称")
    consent = sub.add_parser("confirm-update", help="在交互式终端记录绑定方案的批准")
    consent.add_argument("--plan", required=True)
    sub.add_parser("diagnostics-plan", help="先生成不含账号正文的本地待分享清单，不上传")
    diagnostic_export = sub.add_parser("diagnostics-export", help="把已审阅清单导出到本地文件，不上传")
    diagnostic_export.add_argument("--plan", type=Path, required=True)
    diagnostic_export.add_argument("--output", type=Path, required=True)
    revision = sub.add_parser("confirm-revision", help="在本地交互终端查看具体研究修订并记录玩家回复")
    revision.add_argument("--account", required=True)
    revision.add_argument("--plan", required=True)
    args = parser.parse_args(argv)
    context = Context(args.data_dir, offline=args.offline)
    if args.command == "mcp":
        from companion.mcp_server import serve
        return serve(Registry(context))
    try:
        if args.command == "configure-codex":
            from companion.adapters.codex import install_codex
            from companion.storage import SafeRoot
            files = SafeRoot(args.root)
            state = json.loads(files.path("install-state.json").read_bytes())
            result = ToolResult(data=install_codex(args.workspace, files.path("versions/"+state["current"]["digest"]+"/runtime/python.exe"), Path(state["data_dir"]), offline=args.offline))
        elif args.command in {"diagnostics-plan", "diagnostics-export"}:
            from companion.diagnostics.redaction import prepare_diagnostics, export_diagnostics
            result = ToolResult(data=prepare_diagnostics(args.data_dir) if args.command == "diagnostics-plan" else export_diagnostics(args.plan, args.output))
        elif args.command in {"install-program", "rollback-program", "uninstall-program", "recover-program"}:
            from companion.install import Installer
            from companion.release.artifacts import MAX_ARTIFACT
            from companion.release.signing import load_trust
            manager = Installer(args.root, args.data_dir, trusted_keys=load_trust(args.trust), allow_test=getattr(args, "allow_test", False))
            if args.command == "install-program":
                with args.package.open("rb") as stream:
                    content = stream.read(MAX_ARTIFACT+1)
                data = manager.install(content)
            elif args.command == "rollback-program":
                data = manager.rollback()
            elif args.command == "recover-program":
                data = manager.recover()
            else:
                data = manager.uninstall(purge_data=args.purge_data)
            result = ToolResult(data=data)
        elif args.command == "confirm-revision":
            from companion.memory.revisions import Revisions
            reference = Revisions(context.store).confirm_terminal(args.account, args.plan, stdin=sys.stdin, stdout=sys.stderr)
            result = ToolResult(data={"confirmation_id": reference, "applied": False})
        elif args.command == "confirm-update":
            from companion.policy import ConsentPolicy
            reference = ConsentPolicy(context.store).confirm_terminal(args.plan, stdin=sys.stdin, stdout=sys.stderr)
            result = ToolResult(data={"confirmation_id": reference, "installed": False})
        elif args.command == "call":
            if args.input == "-":
                raw = sys.stdin.buffer.read(262145)
            else:
                with Path(args.input).open("rb") as stream:
                    raw = stream.read(262145)
            if len(raw) > 262144:
                raise CompanionError(ErrorCode.INVALID_INPUT, "请求文件超限")
            from companion.knowledge.package import unique_object
            result = Registry(context).invoke(args.operation, json.loads(raw, object_pairs_hook=unique_object))
        else:
            result = Registry(context).invoke(args.command, {})
    except (OSError, ValueError, RecursionError):
        result = ToolResult.failure(CompanionError(ErrorCode.INVALID_INPUT, "请求输入或文件无效"))
    except sqlite3.Error:
        result = ToolResult.failure(CompanionError(ErrorCode.INTERNAL_FAILURE, "个人数据库操作失败；保留原资料并检查恢复记录"))
    except CompanionError as error:
        result = ToolResult.failure(error)
    sys.stdout.write(canonical(result.to_dict()).decode() + "\n")
    return result.exit_code


