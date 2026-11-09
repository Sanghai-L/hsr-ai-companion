# Codex 本地开发适配

安装器生成项目 .codex/config.toml 和 AGENTS.md 中的管理块，共同规则唯一来源为 adapters/common/RULES.md。解释器、工作目录、数据目录都用绝对路径；不修改用户全局配置，不改变信任状态或批准策略，不为写工具设置免批准。

项目 MCP 配置须由宿主信任该目录后加载。当前 build 的隔离试验未加载仅用 trust_level 启动覆盖的项目配置，失败日志保留。安装器因此同时生成 `.hsr-companion/打开助手.ps1`：以每次会话的完整 MCP 参数启动 Codex，并继续读取项目 AGENTS.md。这个已测兼容入口不修改全局信任或批准策略，也不等同于已验收持久项目信任流程。已有同名未受管服务器、损坏配置或用户编辑过的规则文件会报告冲突；重复安装不重复注入。

P2 同时安装 research、discussion、memory 三个项目技能到 `.agents/skills`，保留用户同名文件和手工修改。公开 UID 导入需要玩家明确请求；研究修订需要对应可信回复记录。当前原生 Codex 没有业务回复回执转接器，可在本地交互终端用 `companion --data-dir <目录> confirm-revision --account <账号> --plan <方案>` 查看并记录一次确认，再执行修订；模型参数不能自行确认。

依据：[官方 MCP 配置](https://learn.chatgpt.com/docs/extend/mcp)、[配置与项目信任](https://learn.chatgpt.com/docs/config-file/config-basic)、[AGENTS.md 发现](https://learn.chatgpt.com/docs/agent-configuration/agents-md)、[项目技能发现](https://learn.chatgpt.com/docs/build-skills)。本轮只验收 Codex；Claude Code、DSH 延续用户暂缓决定，仅保留共用规则模板，不宣称实际适配通过。

