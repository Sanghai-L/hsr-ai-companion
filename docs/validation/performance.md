# 本地性能与故障验证

2026-11-09最终代码复测：Windows11 build26200 x64，AMD Ryzen9 9955HX，Python3.12.10。工具计时不含宿主模型或外网延迟；不是其他机器的保证。

| 项目 | 样本数 | P50(ms) | P95(ms) |
|---|---:|---:|---:|
| account_read | 30 | 21.654 | 23.983 |
| account_write | 30 | 17.736 | 19.822 |
| damage_formula | 30 | 4.925 | 5.653 |
| knowledge_cli_cold_process | 10 | 598.338 | 629.864 |
| knowledge_search_first | 1 | 126.806 | 126.806 |
| knowledge_search_warm | 30 | 53.778 | 64.041 |
| knowledge_signed_local_sync_cold | 10 | 115.204 | 123.37 |
| optional_legacy_batch_two | 3 | 2939.035 | 3026.868 |
| optional_legacy_single | 5 | 1204.264 | 1229.171 |
| representative_batch_four | 20 | 48.821 | 53.806 |
| representative_single_comparison | 30 | 40.654 | 44.968 |

本地检索、普通公式和冷进程检索满足本轮约1秒初始目标。旧后端单场／双场样本仅5／3，不把小样本尾延迟或可选后端性能当全体玩家承诺。

已注入真实进程崩溃、超时回收、MCP断开、安装迁移阶段退出、跨进程共享锁与并发研究写入、磁盘不足和损坏数据库。同步比较按动作／候选／墙钟预算停止，部分结果不排名，无后台工作队列；不宣称断点续算。

最终计时原始样本：.local/evidence/D053/533f0a7cfa/performance.json；早期7a60c7829f记录保留。对应故障与安装证据见D053和D051目录。
