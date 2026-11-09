"""Public operator instructions for implemented CLI commands; contains no local paths."""
from companion.contracts import ToolResult


def local_help(topic="all"):
    sections = {
        "diagnostics": {"prepare": "companion --data-dir <个人目录> diagnostics-plan",
                        "review": "先阅读返回的 share-plan.json 与 diagnostics.json；不会上传",
                        "export": "companion diagnostics-export --plan <share-plan.json路径> --output <新的zip路径>",
                        "default_excludes": ["UID", "账号ID", "研究正文", "原始快照", "凭据", "配置", "本机路径"],
                        "automatic_upload": False},
        "install": {"media_entry": "Install-HSR.ps1 -Workspace <玩家项目> -Offline（离线时）",
                    "first_install": "companion --data-dir <个人目录> install-program --root <程序目录> --trust <固定公钥文件> --package <程序包>",
                    "configure": "companion --data-dir <个人目录> configure-codex --root <程序目录> --workspace <玩家项目>",
                    "recover": "companion --data-dir <个人目录> recover-program --root <程序目录> --trust <固定公钥文件>",
                    "rollback": "companion --data-dir <个人目录> rollback-program --root <程序目录> --trust <固定公钥文件>",
                    "uninstall": "companion --data-dir <个人目录> uninstall-program --root <程序目录> --trust <固定公钥文件>",
                    "uninstall_preserves_personal": True,
                    "explicit_personal_cleanup": "单独选择 --purge-data；个人目录改名隔离，仍可手工恢复",
                    "failure_policy": "保留旧可用版本和个人资料；备份／候选自检后才切换，不覆盖运行中的旧依赖"},
        "updates": {"detect": "updates_check 或 program_update_propose；均不安装代码",
                    "confirm": "companion --data-dir <个人目录> confirm-update --plan <方案ID>（本地交互终端）",
                    "apply": "program_update_apply(plan_id, confirmation_id) 消费匹配的已记录确认",
                    "scope": "确认绑定版本、包指纹和程序路径；公共知识同步、UID刷新各自独立",
                    "existing_confirmation": "同一有效方案已有确认就直接消费，不重复询问；模型参数不能生成确认"}}
    return ToolResult(data={"sections": sections if topic == "all" else {topic: sections[topic]},
                            "command_policy": "全局 --data-dir／--offline 位于子命令之前；脚本入口可代为使用项目自带运行时",
                            "executed": False})
