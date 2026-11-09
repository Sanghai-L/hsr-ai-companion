"""D009: audit the completed scope, record the decision, and stop at the P0 gate."""
import json
import re

from common import ROOT, LOCAL, now, digest, code_snapshot, write_json, update_task
from validate_p0 import validate, read


def main():
    update_task('D009','IN_PROGRESS',summary='按用户最终 Codex 范围核对 P0 全部证据与后续机制缺口',
                next_step='离线关口验证、固定基线、记录结论',level='本地阶段关口')
    preflight=validate(require_gate=False)
    write_json(LOCAL/'evidence/D009/preflight.json',preflight)
    baseline=read('docs/requirements/baseline.json')
    baseline['p0_user_adjusted_host_scope']={'validated':['codex'],'user_deferred':['claude-code','dsh'],
        'decision_record':'docs/requirements/local-decisions.md'}
    write_json(ROOT/'docs/requirements/baseline.json',baseline)
    # Preserve owners from D001; update evidence without claiming later features.
    old=(ROOT/'docs/requirements/traceability.md').read_text(encoding='utf-8')
    owners={parts[1].strip():parts[3].strip() for line in old.splitlines()
        if re.match(r'^\| A\d{2} \|',line) and (parts:=line.split('|'))}
    design=(ROOT/'HSR_AI_Companion_完整实现规划_v1.0.md').read_text(encoding='utf-8')
    requirements={aid:(title.strip(),condition.strip()) for aid,title,condition in
        re.findall(r'^\| (A\d{2}) \| ([^|]+) \| ([^|]+) \|$',design,re.M)}
    evidence={
        'A01':'D002 中文空格路径解释器实测；干净机器业务安装待后续',
        'A02':'D005 Codex 两次新会话规则/探针通过；另两宿主用户暂缓；业务初始化待后续',
        'A03':'D004 两个隔离合成账号；实际账号切换逻辑待后续',
        'A04':'D006 实际 Showcase 边界与未知字段；导入器待后续',
        'A05':'D006 原创合成故障样本；实际合并/保留旧快照待后续',
        'A06':'D006 一次显式公开例子请求；业务刷新策略待后续',
        'A07':'D004 种子输入；记忆实现与跨会话行为待后续',
        'A08':'D004 冲突输入；确认及历史实现待后续',
        'A09':'D001 权限基线；实际公共库写保护待后续',
        'A10':'D001 三类更新分离；同步事务待后续',
        'A11':'D001 更新权限基线；更新器及恢复待后续',
        'A12':'D003 固定版本、D007 数据差异记录；业务兼容拦截待后续',
        'A13':'D007 冻结历史 4.4.1 来源哈希；未宣称当前关卡',
        'A14':'D007 只使用已上线历史样例；业务未上线隔离待后续',
        'A15':'D004 错误前提与反例种子；行为评测待后续',
        'A16':'保留 PRD A/B 风格；业务实现待后续',
        'A17':'D008 两个独立历史公式例子与真实事件算术；正式计算器待后续',
        'A18':'D008 缺口机读清单；严格模拟预检实现待后续',
        'A19':'D008 两队各两次相同输入/种子全事件复放；正式公平比较工具待后续',
        'A20':'D007 一个混沌历史场景；四模式正式模拟待后续',
        'A21':'D004 预算与未知保底样本；概率及规划实现待后续',
        'A22':'D008 修复三种模式的 AV 预算；任务取消/恢复待后续',
        'A23':'P0 探针只返回固定文本；网页攻击及工具边界业务测试待后续',
        'A24':'私有资料留 .local；共享样本无真实 UID；正式发布扫描待后续',
    }
    lines=['# 需求追踪','',f'更新：{now()}。原 PRD、原规划保持原文；本轮宿主范围依用户追加指示调整。',
        'P0 是可行性证据；下面的最终验收条件仍由原责任任务完成。','',
        '| 验收 | 需求 | 最终责任任务 | P0 实际证据与未完成范围 |','|---|---|---|---|']
    for aid in sorted(requirements):
        lines.append(f'| {aid} | {requirements[aid][0]} | {owners[aid]} | {evidence[aid]} |')
    lines+=['','| 用户补充 | 当前执行 |','|---|---|',
        '| 仅 Windows | 原生 Windows + Python 3.12 验证 |',
        '| 无交付期限 | 阶段验收驱动；不以日历代替质量关口 |',
        '| 本轮执行 P0 | 任务 001～009 |',
        '| Claude Code 先不适配 | 用户明确暂缓；未测 |',
        '| DSH 本轮先暂缓验收 | 保留 MISSING_CREDENTIAL 实录；当前宿主验收只有 Codex |']
    (ROOT/'docs/requirements/traceability.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    adr=['# ADR-002：P0 后续实现基线','',f'日期：{now()}；状态：接受用于后续工程，范围受下述覆盖限制。','',
        '## 决定','',
        '1. 使用原生 Windows、Python 3.12，MCP stdio 为主、CLI 为排错入口。当前实际宿主基线只有 Codex 0.166.0-alpha.5.1；Claude Code 适配及 DSH 验收按用户指示暂缓。',
        '2. HSR_Nous `f8935ddb407b297732fbd3c624d55897e3e648b9` 作为主模拟核心，附 0001 AV 预算补丁。不整体引入其模型、账号登录、网页和数据自动更新链路。',
        '3. 固定 uv 0.13.7 与已实测核心依赖。具体版本、下载摘要及哈希见两个 lock 清单。本次隔离验证未修改全局 Python，未使用 WSL、Docker，未主动申请管理员提权。',
        '4. 公共账号资料采用 Enka 公开 Showcase 路线；字段以本次实际响应为边界。正式导入器在 D024 实现；TTL 不赋予自动刷新权限，不获取 Cookie。',
        '5. 首个工程场景固定为历史 4.4.1／1034／扫除风暴／12 层上半；队伍 A：1408、1412、1313、1414；队伍 B：1308、1006、1106、1304。属于合成无装备构筑；正式产品验收队伍后续再确认。',
        '6. 个人结构化数据采用 SQLite，研究正文采用 Markdown；这是后续架构决定，存储事务和恢复尚由 D013 验收。公共知识与程序、个人资料分别更新。',
        '7. 不采用许可未明确的 hsr-mechanic-sim 代码。其他数据候选本轮仅作私有参考；整体许可证继续保持未决定，预算补丁保留上游 MIT 通知。','',
        '## 证据','',
        '- D001：原 PRD 哈希与副本一致，两份原规划哈希未变，58 项任务与 24 项验收责任齐全。',
        '- D002：三个隔离环境在中文空格路径中真实启动并回读 UTF-8；未改系统默认解释器。',
        '- D003：八个候选固定完整 SHA；许可、文档与调用入口核对。',
        '- D005：Codex 两次实际新会话均调用探针并返回规则标记；搜索与指定 URL 获取分别成功；真实失败尝试保留。',
        '- D006：一次公开文档样例查询 HTTP 200，展示 8 人、ttl=60；完整账号和资源不可默认读取。',
        '- D007：冻结来源字节哈希和明确历史期数；发现跨数据域不同步，未用 Release 日期推断所有数据最新。',
        '- D008：202 个相关测试通过、一个明确不在核心范围的 FastAPI 测试 deselected；两队各两次真实模拟无截断，完整状态/事件/日志一致；另有独立公式与事件算术检查。','',
        '## 继续与限制','',
        '结论为继续使用现有核心，不从零重写全引擎。当前证据足以推进基础工程，不能推出首个关卡的游戏结果可信度已达标。',
        '',
        '高精度阻断包括敌人 AI/阶段、场景等级与精英系数、抗性导入、角色 caveats 和游戏控制实测。责任与状态在 `manifests/simulator-gaps.json`；D035/D036 必须默认拒绝这些资料不完整的精确请求，D038/D042 负责补齐及外部校准。',
        '',
        '后备路线是保留公式、调度、资源和模板框架，替换具体角色/敌人模板或局部适配器；如果首个场景的必要机制无法有界修复，则重做 D008。SRSim 当前不作为完整队伍的现成替代；不因工程受阻删除完整模拟目标。',
        '',
        '先前工作量区间仍是建议，P0 没有证据把整场高精度开发缩减为简单包装。最优先的风险任务是 D035/D036/D038/D042，而非按模板文件数量扩大支持声明。',
        '',
        '下一任务是 D010。P1 在后续开发请求中启动；本次 P0 账本不会自动把后续任务标为进行中。']
    (ROOT/'docs/decisions/ADR-002-implementation-baseline.md').write_text('\n'.join(adr)+'\n',encoding='utf-8')
    gate={'schema_version':1,'at':now(),'status':'PASS_USER_ADJUSTED_SCOPE','host_scope':['codex'],
        'user_deferred':['claude-code','dsh'],'original_three_host_requirement_met':False,
        'whole_game_accuracy_verified':False,'backend':'hsr-nous',
        'upstream_commit':'f8935ddb407b297732fbd3c624d55897e3e648b9',
        'core_tests':{'passed':202,'failed':0,'skipped':0,'deselected':1,
            'exclusion_reason':'optional FastAPI presentation test; not installed in core probe'},
        'team_runs':4,'full_event_replays_equal':True,'uid_live_requests':1,
        'original_prd_sha256':baseline['sha256'],'next_task':'D010',
        'future_precision_gate':'D042; first fill D035/D036/D038 gaps',
        'decision':'Continue with pinned core plus bounded repair; precision blocked for unsupported scenario mechanics'}
    write_json(ROOT/'docs/gates/P0.json',gate)
    lines=['# P0 阶段关口','',f'日期：{gate["at"]}。结论：**按用户调整后的范围通过 P0 可行性关口**。','',
        '本轮完成任务 D001～D009；当前实际验证宿主只有 Codex。Claude Code 适配、DSH 验收由用户明确暂缓，原始三宿主要求没有被冒称已完成。','',
        '| 验证层次 | 实际结果 |','|---|---|',
        '| 需求与账本 | PRD 原文哈希一致；原两份规划未覆盖；58 个任务、24 项验收责任 |',
        '| Windows | Python 3.12.10、中文空格路径、三个隔离环境 UTF-8 实测 |',
        '| 来源与许可 | 8 个候选完整 SHA；许可摘要、文件哈希、排除清单 |',
        '| 实际 Agent | Codex 两次独立新会话的规则与探针；搜索/获取分别成功 |',
        '| 公开 UID | 一次明确公开文档样例的真实 200 响应；8 个原创合成边界 fixture |',
        '| 场景 | 冻结已上线历史 4.4.1 的混沌 12 层上半，来源与缺字段可追溯 |',
        '| 模拟与回归 | 202 passed、0 failed、0 skipped、1 个解释清楚的范围排除；修复真实 AV 预算问题 |',
        '| 后端真实执行 | 两支四人队各两次实际模拟、无截断、完整事件和状态重放一致；未调用外部模型 |',
        '| 独立算术抽查 | 2 个历史实测公式例子、4 个实际伤害乘区检查、SP 与首次行动值检查 |','',
        '这里通过的是工程路线可行性。首个关卡的高精度仍被敌人机制、场景系数、抗性、角色 caveats 与游戏控制实测阻断；当前近似结果禁止用于实际队伍排名或抽卡建议。','',
        '主路线：Python + MCP stdio + HSR_Nous 固定 commit 和一份预算补丁。具体决定见 [ADR-002](../decisions/ADR-002-implementation-baseline.md)，未支持范围见 [模拟验证报告](../feasibility/simulator-probe.md)。','',
        '默认离线总验收：`python -X utf8 tools/p0/validate_p0.py`；共享材料自检增加 `--shared-only`。原始日志和私人查询响应仅在 `.local/evidence/`，不进入共享文件。','',
        '下一项为 D010：创建正式业务包、统一验证入口和默认离线测试边界；后续任务保持 NOT_STARTED。']
    (ROOT/'docs/gates/P0.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    # Check gate artifacts before recording completion.
    checks=validate(require_gate=False)
    update_task('D009','DONE',summary='按用户最终 Codex 范围通过 P0 可行性关口；固定主后端、补丁与精度阻断责任',
        artifacts=['docs/decisions/ADR-002-implementation-baseline.md','docs/gates/P0.md','docs/gates/P0.json'],
        commands=['python tools/p0/finalize_p0.py','python tools/p0/validate_p0.py','python tools/p0/validate_p0.py --shared-only'],
        counts={'passed':checks['passed'],'failed':0,'skipped':0,'scope':'Codex; other two hosts explicitly deferred by user'},
        evidence=['.local/evidence/D009/preflight.json','.local/evidence/D009/validation.json'],
        next_step='D010（后续开发阶段）',level='阶段证据汇总；不等于完整产品或游戏精度认证')
    final=validate()
    write_json(LOCAL/'evidence/D009/validation.json',final)
    print(json.dumps({'gate':gate['status'],'local_checks':final['passed'],'p0_tasks_done':9,'next_task':'D010'},ensure_ascii=False))


if __name__=='__main__':
    main()
