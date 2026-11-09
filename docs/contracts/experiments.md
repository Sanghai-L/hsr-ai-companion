# 实验与比较合同（P3）

所有计算通过同一 `experiment` 输入：schema_version、kind、conditions、versions、budget、parameters、source_refs、assumptions。kind 为 damage、timeline、gacha、pull_plan；simulation 已有构筑和覆盖预检合同，完整执行能力仍未交付，见 simulation.md。真实账号口径必须填写 snapshot_id；等投资、理想上限和纯合成条件分开。

当前 engine 为 0.1.3，受控规则为 p3-1；执行时检查安装版本。knowledge 与 data 是本次输入实际使用的资料版本，不能只填“最新”。预算包括 max_events（1～300）、max_av（大于0，最多100000）、max_transitions（最多3000000）和 max_seconds（大于0，最多30秒）。时序执行事件／AV／墙钟限制，概率和规划共享状态／墙钟限制；整体会话研究预算由宿主规则约束。

内容指纹采用 UTF-8、NFC 字符规范化、有序对象键与紧凑 JSON，等值整数和浮点及负零统一。数组顺序保留，因为角色、技能、阶段和事件顺序可能影响结果；来源与假设也按提供顺序保留。只排除顶层 run.task_id／run.started_at。未来收入日期等业务时间不能被排除。NaN／Infinity 拒绝。result_fingerprint 对实际数值输出另行哈希，不代表游戏精度认证。

输出沿用统一 ToolResult，含规范化输入、输入／结果指纹、来源、版本、假设、限制及缺失字段。`calculate` 和 `plan_pulls` 为只读计算，不创建账号、不刷新 UID、不修改记忆、公共知识或程序。重要结论如需保存，由 Agent 按原个人记忆流程追加，存在冲突则仍走具体方案确认。

`experiment_compare` 检查 kind、conditions、versions、budget、source_refs、assumptions；parameters 是实验因素，允许变化。不同计算层级拒绝比较；不同版本、模式、投资、预算或资料口径必须给 declaration，并返回 ranking_permitted=false。未说明差异时返回 VERSION_INCOMPATIBLE，不会生成排名。D040 会在同一合同上增加完整模拟公平比较。

参数 schema 在工具清单内完整展开；若宿主呈现不完整或 Agent 不确定字段，可调用只读 calculation_schema(kind)，获取该层级完整合同、当前版本、单位与原创合成请求示例，安装包内自带，无需读源码或开发目录。示例不得当作玩家账号事实。独立计算工具 schema：damage-parameters、timeline-parameters、gacha-parameters、pull-plan-parameters。全部拒绝未知字段和可执行表达式。概率规则只接受受限数值数组，不执行任何 DSL。

样例位于 tests/fixtures/requests；独立基准位于 benchmarks/formulas。CLI 示例：

```powershell
.\.venv\Scripts\python.exe -m companion --data-dir '.local/p3-demo' --offline call calculate --input tests/fixtures/requests/damage.json --json
.\.venv\Scripts\python.exe -m companion --data-dir '.local/p3-demo' --offline call calculate --input tests/fixtures/requests/timeline.json --json
.\.venv\Scripts\python.exe -m companion --data-dir '.local/p3-demo' --offline call calculate --input tests/fixtures/requests/gacha.json --json
.\.venv\Scripts\python.exe -m companion --data-dir '.local/p3-demo' --offline call plan_pulls --input tests/fixtures/requests/pull-plan.json --json
```
