# 维护就绪关口

2026-11-09：D058通过。组合演练使用真实嵌入式运行时、SQLite和测试签名包；下一版本、时钟、接口响应与批准适配均为封闭合成，不是实际0.1.4发布、真实用户回执或游戏校准。

知识0.5.0→0.5.1在可控TTL时钟下自动同步，旧研究正文保持，冲突方案仍等待确认。程序0.1.4在确认前只提出方案，绑定的一次性确认后才实际切换。合成新规则将测试配置结果改为12420；同一历史实验调用原0.1.3签名快照仍重算9720，旧实验载荷未变。

本地合成UID接口结构变化被归类为VERSION_INCOMPATIBLE，账号与旧快照保持，真实UID HTTP请求为0。损坏的新知识恢复为上一有效0.5.0；撤回用更高的纠正版0.5.2，不重写同版本。程序回滚至0.1.3后，新旧私人研究均保留，未批准研究方案仍未应用。

执行：python -m pytest tests/maintenance/test_version_change_drill.py -q -ra；1项组合演练通过。详细本机证据：.local/evidence/D058/drill.json和drill.xml。维护步骤见[runbook](../maintenance/runbook.md)，候选指纹见[P6关口](P6-release-candidate.md)。
