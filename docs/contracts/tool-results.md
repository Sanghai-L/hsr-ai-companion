# 工具结果合同

CLI 和 MCP 共用 `ToolResult`，所有字段固定为 status、data、sources、versions、assumptions、warnings、missing_fields、error。success／partial 的 error 必须为空，error 状态必须带独立错误码和 retryable；null 保留未知，0 保留已知零。来源附类型、引用、带时区观察时间，抓取时间不替代游戏版本。

错误码覆盖输入、缺资料、未支持、网络、版本、确认、冲突、预算及内部故障。退出码：0 成功，2 输入或授权拒绝，3 缺项或降级，4 执行故障。JSON Schema 位于 schemas/，安装 wheel 时随包携带；编辑版和 wheel 使用同一合同。

实体使用角色 ID 与形态 ID 的组合；装备使用实例 ID。数值状态、信息状态、证据、模拟覆盖分别表达。百分数／百分点除以 100 得到比例；公开面板与基础面板分开，拒绝再次叠加装备。时间含时区，版本未知保持 null；跨版本只允许显式假设并输出限制。

