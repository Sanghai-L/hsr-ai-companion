---
name: memory
description: 追加和找回星穹铁道账号私有研究，区分事实、假设和有条件结论，并通过冲突方案与玩家确认修订旧结论。
---

memory_search 按账号、实体、主题和版本寻找摘要，需要全文才 memory_read。摘要保留分类、条件、版本与待处理冲突；未确认的旧结论和新证据都要让玩家看见，不能默认新说法已经替换历史。

memory_append 只能追加。事实需要明确来源，假设保持 hypothesis，结论需 claim_key、适用条件和证据／实验引用；同论点不同表述仍应识别为潜在冲突，不靠换键绕开修订。普通追加不更新账号数值，玩家资料走 account_patch。

新证据用 evidence_register 登记，再 memory_conflict_propose 关联旧记录，提出替换、限制条件或废止的具体方案。用 memory_revision_get 审阅完整内容，等待玩家对这个方案的回复。没答复时旧正文不变，当前回答可解释新证据。

memory_revision_apply 需要已有可信回复记录的 confirmation_id，并绑定 expected_id。沿用同一方案已记录的确认，不重复询问。旧版本变化时重新核对方案；重复执行返回同一次结果，历史正文保留。

当前 Codex 无可核验的业务回复回执连接器：提示本地 `companion --data-dir <目录> confirm-revision --account <账号> --plan <方案>`，它展示具体方案并记录一次确认。不得自行运行该命令来代替玩家回复，不提供 confirmed=true 或编造 confirmation_id。已有可信确认编号时直接执行。受控验收回执适配只用于隔离测试。
