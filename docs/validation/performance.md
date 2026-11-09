# 本地性能与故障验证

2026-11-09；Windows 11 build 26200、x64、Python 3.12.10。测量不包含宿主模型响应和外网延迟。全部样本保存在 .local/evidence/D053/7a60c7829f/performance.json。

| 项目 | 样本数 | P50（ms） | P95（ms） |
|---|---:|---:|---:|
| account_read | 30 | 21.851 | 24.14 |
| account_write | 30 | 16.531 | 18.848 |
| damage_formula | 30 | 3.753 | 4.769 |
| knowledge_cli_cold_process | 10 | 464.63 | 490.966 |
| knowledge_search_first | 1 | 91.606 | 91.606 |
| knowledge_search_warm | 30 | 42.056 | 44.04 |
| knowledge_signed_local_sync_cold | 10 | 140.483 | 150.209 |
| optional_legacy_batch_two | 3 | 2481.659 | 2542.015 |
| optional_legacy_single | 5 | 977.307 | 4049.742 |
| representative_batch_four | 20 | 46.198 | 63.938 |
| representative_single_comparison | 30 | 31.073 | 33.421 |

本地热检索、简单公式和冷进程检索均达到本轮约1秒目标。首次检索只有1个样本；可选旧后端仅5次单场与3次双场，尾延迟统计只反映本轮样本。旧后端没有打进玩家包，不把它的性能等同于默认简化比较。

实际故障用例包含计算子进程崩溃／超时后已回收、MCP EOF退出、安装迁移阶段进程直接退出后的日志恢复、四个并发进程跨两账号写入32条研究，以及磁盘写失败保留旧研究。同步比较还验证动作、候选、墙钟预算和协作取消；取消后不对部分结果排名。默认简化路径不启动后台工作进程，没有提供长作业队列或断点续算。

验证命令：python -m benchmarks.performance.run；python -m pytest tests/reliability tests/jobs tests/install tests/storage tests/updates -q -ra。后者39项通过，均为离线／真实本地进程层；不替代真实宿主模型行为。
