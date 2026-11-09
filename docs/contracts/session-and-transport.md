# 会话与调用合同

CLI 的全局参数在子命令之前：`--data-dir` 指定独立私有根，默认 `.local/companion`；`--offline` 禁止整个调用的外网请求，但允许明确配置的本地维护者测试源。`doctor` 和 `status` 在新目录不写入、不初始化、不联网。`call` 与 MCP 共用注册表和结果合同，输入限 256 KiB，领域结果限 64 KiB，能力与工具发现分页；无该阶段能力则返回 UNSUPPORTED，不伪造空成功。

MCP 使用逐行 JSON-RPC，完成 initialize 与 initialized 通知后才能调用工具；支持标准 `_meta`。stdout 仅协议，诊断写 stderr。一个连接缓存最近 128 个请求 ID 的响应；相同 ID／内容返回同一结果，不同内容拒绝。跨进程不承诺任意请求去重；账号配置使用稳定 ID、知识同步与更新方案另有幂等策略。EOF 后不留后台服务。

`session_bootstrap` 恢复默认账号、风格、待初始化字段、相关记忆摘要与冲突，恢复研究索引并按间隔检查知识与程序发布源。UID 只在明确请求的 account_refresh 中导入；普通调用不会查询，未导入时返回 pending。没有风格时明确询问 A／B，两个账号独立，可后续更改。status 不含原始 UID；account_get 在本地明确账号上下文中分页返回字段，使用只读数据库，账号读操作不隐式初始化。account_patch 带完整内联字段合同、预期快照、来源和确认标记，保存新快照并返回精简摘要，未知不补零。已有 UID／区服不可静默换绑到另一个账号身份。

本机 config.json 只允许 knowledge_source、program_source、check_interval。远程源为明确 HTTPS release.json 地址；本地源为绝对目录，含 release.json。内置32条有来源的起始知识，源未配置时仍可检索并保持unconfigured，不称最新。P6初装可合并签名包绑定的维护者来源，已有玩家配置保持不变；运行时校验索引与内容签名。扩展知识包至少要求程序0.1.1。旧三条测试包仅保留开发测试路径。

协议依据：[MCP tools 规范](https://modelcontextprotocol.io/specification/2025-11-25/server/tools)。

