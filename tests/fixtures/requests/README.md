# 可重放请求

全局 `--data-dir` 和 `--offline` 放在 `call` 前。知识读取会重建派生索引，不创建账号，也不联网。

| 文件 | 操作 | 前置 | 预期退出码与断言 |
|---|---|---|---|
| knowledge_search.json | knowledge_search | 内置首批知识 | 0；Top-5 包含 debuff-once；附来源、版本和例外 |
| account_get.json | account_get | `python tools/prepare_demo.py --data-dir .local/demo-new` 创建的新合成目录 | 0；demo-a，stellar_jade=1600，uid_refreshed=false；非真实 UID |
| damage.json | calculate | 无账号需求 | 0；固定状态普通直伤 2025，逐乘区可手算 |
| timeline.json | calculate | 无账号需求 | 0；SPD100 在 AV50 变为 200，行动时点 75、125、175 |
| gacha.json | calculate | 合成小卡池 | 0；预算 1 抽获得概率 0.5；期望消耗 1.5 抽 |
| pull-plan.json | plan_pulls | 合成预算、收入与假设日期 | 0；单目标三情景概率 0.5/1/1，双目标共用预算 0/0.25/0.75；含不抽 |
| simulation.json | simulation_preflight | 无账号、无后端安装要求；历史4.4.1工程构筑 | 3；partial，明确敌人AI／阶段缺口，game_ranking_allowed=false；改为high时拒绝 |

示例：`python -m companion --data-dir .local/demo --offline call knowledge_search --input tests/fixtures/requests/knowledge_search.json --json`。
# P4／P5补充样例

`comparison.json` 通过 `simulation_compare` 比较明确假设的单目标200AV窗口，预期退出0、丹恒队9720／黑塔队5940；不是成熟队伍或玩家练度。四模式完整样例可由 `analysis_schema(mode)` 获取，对应 `benchmarks/modes/{moc,pf,as,aa}/representative-v1.json`。

`evals/cases/multi-team.json` 供 `multi_team_plan` 使用，三骑士候选和12名角色可用性均为明确假设。`sensitivity.json` 用 `sensitivity_analyze` 做目标数复算。所有这些只读调用不查UID、不创建账号或保存研究。`comparison_save` 和记忆工具需先在指定测试目录配置合成账号。

