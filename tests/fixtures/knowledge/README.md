# P1 原创知识包样本

source/ 只含 combat、characters、basics 三类，各有一条原创工程测试知识及其元数据；它们不代表游戏机制准确性或正式服版本覆盖。不含第三方原文、真实 UID、执行规则和 Agent 指令。

可用 tools/p1/create_knowledge_fixture.py 重建；build_package() 根据明确版本和兼容范围生成规范化 JSON 清单、正文哈希及包指纹。同一输入和版本产生完全相同字节。README 不在 source/ 内，构建器不会把它打入知识包。

