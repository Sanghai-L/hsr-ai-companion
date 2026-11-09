"""D008 completion: real execution evidence, limitations, and repair provenance."""
import json
import re
from common import ROOT, LOCAL, now, digest, write_json, update_task


def main():
    folder=LOCAL/'evidence/D008'
    summary=json.loads((folder/'simulation-summary.json').read_text(encoding='utf-8'))
    core=json.loads((folder/'core-tests.json').read_text(encoding='utf-8'))
    events=json.loads((folder/'event-checks.json').read_text(encoding='utf-8'))
    assert core['exit_code']==0 and '202 passed, 1 deselected' in core['stdout']
    assert events['exit_code']==0 and len(events['formula_checks'])==2
    assert all(t['runnable'] and t['replay_identical'] and not t['truncated'] for t in summary['teams'])
    patch=ROOT/'patches/hsr-nous/0001-bound-av-with-pending-waves.patch'
    gaps=[
        {'id':'SIM-001','title':'待后续波次时忽略 AV 预算','status':'FIXED_LOCAL_PATCH',
         'evidence':'tests/p0/test_simulator_budget.py；原版三种模式均失败，补丁后三种通过',
         'patch_sha256':digest(patch),'owners':['D035','D039'],'blocks_precise_results':False},
        {'id':'SIM-002','title':'stage_template 引用未实现','status':'CONFIRMED_GAP',
         'evidence':'StageCompiler.compile 对 stage_template 抛 NotImplementedError；本轮显式组装 inline 输入',
         'owners':['D035','D038'],'blocks_precise_results':True},
        {'id':'SIM-003','title':'首个场景三种敌人只有占位普攻、没有完整 AI／阶段机制','status':'CONFIRMED_GAP',
         'evidence':'generate_enemy_template 的 notes 和动作结构；本轮真实输入/事件保存在 .local',
         'owners':['D035','D038','D043'],'blocks_precise_results':True},
        {'id':'SIM-004','title':'敌人默认系数与关卡指定等级／精英组不一致','status':'CONFIRMED_GAP',
         'evidence':'enemy-template-audit.json：模板使用实例默认组，冻结场景指定 hard=3、elite=164；未应用该覆盖',
         'owners':['D035','D038'],'blocks_precise_results':True},
        {'id':'SIM-005','title':'enemy_template 路径没有导入完整抗性和特殊减伤','status':'CONFIRMED_GAP',
         'evidence':'StageCompiler._compile_enemy 的模板字段；缺口不能靠默认抗性或默认数值冒充精确输入',
         'owners':['D035','D038'],'blocks_precise_results':True},
        {'id':'SIM-006','title':'角色模板 caveats 与表达式刷新告警','status':'COVERAGE_LIMITATION',
         'evidence':'队伍 A 4 条、队伍 B 37 条 caveats；另有 1313／1414 的 stack_mode 告警及白厄技能指向提示',
         'owners':['D036','D043'],'blocks_precise_results':True},
        {'id':'SIM-007','title':'全场游戏准确性与首个场景外部控制实测未完成','status':'NOT_VERIFIED',
         'evidence':'仅有历史公开伤害例子、事件算术检查与模型内同种子复放，没有本机游戏控制实验',
         'owners':['D040','D041','D042'],'blocks_precise_results':True},
        {'id':'SIM-008','title':'更广机制的显式未实现范围','status':'OUTSIDE_P0_CANDIDATES',
         'evidence':'上游 engine_design 中 Aha 特定窗口、续段、资源银行／host provenance；不能按模板文件数宣称完整覆盖',
         'owners':['D036','D043'],'blocks_precise_results':True},
    ]
    write_json(ROOT/'manifests/simulator-gaps.json',{'schema_version':1,'at':now(),
        'backend':'hsr-nous','upstream_commit':'f8935ddb407b297732fbd3c624d55897e3e648b9',
        'local_patch':patch.relative_to(ROOT).as_posix(),'scope':'P0 engineering feasibility only',
        'game_accuracy_certified':False,'gaps':gaps})
    catalog_path=ROOT/'benchmarks/catalog.json'
    catalog=json.loads(catalog_path.read_text(encoding='utf-8'))
    for team in catalog['cases'][0]['teams']:
        actual=next(t for t in summary['teams'] if t['id']==team['id'])
        team.update(runnable=True,replay_identical=actual['replay_identical'],strict_scenario_supported=False,
                    coverage='engineering approximation; blocked for game recommendations',
                    caveat_count=actual['caveat_count'],evidence='.local/evidence/D008/'+team['id']+'-run-1.json')
    write_json(catalog_path,catalog)
    lines=['# 模拟后端可行性验证','',f'记录：{now()}。主后端固定 commit `f8935ddb407b297732fbd3c624d55897e3e648b9`，另有一份本地预算补丁。','',
        '结论：事件引擎与模板链可以作为继续开发的基础；当前 alpha-moc 只达到工程近似执行，不能用于通关预测、队伍排名或抽卡收益建议。','',
        '## 环境与实际调用','',
        '- 原生 Windows、Python 3.12.10。使用本地 uv；锁定依赖见 `tools/p0/simulator-requirements.lock`。',
        '- 核心源码只需要 PyYAML；pytest 和 editable 构建依赖属于验证环境。没有安装 LangChain、账号、网页、optimizer 或浏览器依赖。',
        '- 对锁定源码使用 `uv pip install --no-deps --no-build-isolation -e <本地源码>`；上游完整安装脚本没有执行。',
        '- 两队使用真实 `compile_encounter` → `CombatEngine.from_compiled` → `run`，不是 mock。网络连接、DNS 和任意子进程在模拟过程中由 Python audit hook 拒绝。',
        '- 测试框架的唯一子进程例外是上游用来读取版本的 `git rev-parse HEAD`；没有登录或模型调用。','',
        '## 测试与有界修复','',
        '- 最终相关回归：**202 passed，0 failed，0 skipped，1 deselected**。',
        '- 被排除的是 `test_web_state_payload_caveats`：它验证本轮明确不安装的 FastAPI 呈现层。先前缺 FastAPI 的失败保留在 previous 日志；不作为核心已覆盖项。',
        '- 初次测试还暴露验证器过严阻止 Git 元数据读取、临时目录父目录缺失；已修正验证器，未修改上游断言。',
        '- 真实两队最初均触及 200 动安全上限。进一步定位到后续波次尚未进入时，两个预算判定均附加了 `_has_next_wave()` 条件，令 650 AV 限制失效。',
        '- `tests/p0/test_simulator_budget.py` 在原版的 fixed_av／survival／wipe 三种模式全部失败；本地补丁去掉该条件后通过，且相关上游回归通过。',
        '- 原始截断结果保留在 `.local/evidence/D008/initial-truncated/`；修复补丁、SHA256 和 MIT 通知分别保留在 patches、上游锁和 licenses。','',
        '## 两队实际执行','',
        '场景是已上线历史 4.4.1／1034／12 层上半的编成；E0、80 级、无光锥和遗器；650 AV；初始 3 SP 和 50% 普通能量；roll 模式、seed=42。双方采用相同动作优先级；白厄队的友方目标规则引用策展 demo 的白厄标记。特殊资源按各模板开局规则初始化。','',
        '| 队伍 | 动作数 | 两次耗时（秒） | 完整事件／状态／日志复放 | 截断 | caveats |','|---|---|---|---|---|---|']
    for team in summary['teams']:
        lines.append(f"| {team['id']} | {team['turns']} | {team['seconds'][0]:.4f} / {team['seconds'][1]:.4f} | 一致 | 否 | {team['caveat_count']} |")
    lines+=['','这些耗时只代表本机的近似、固定 650 AV 样例，不是完整关卡性能承诺。双方未清完第一波；未跑到后续 Boss 阶段不等于该阶段已支持。','',
        '## 事件与外部依据','',
        f"- 独立重算两个[公开历史伤害实测例子](https://www.prydwen.gg/star-rail/guides/damage-formula)：未击破 {events['formula_checks'][0]['backend']:.6f}，击破 {events['formula_checks'][1]['backend']:.6f}；后端相同输入与独立算式一致，显示取整分别 312、346。该来源不是当前版本全场认证。",
        '- 分别抽查两队各两个实际伤害事件的乘区乘积；检查两队 SP 变化没有越界；初始两只敌人的首次行动值与 10000/速度相符。',
        '- 抽查能证明输入算术和部分事件自洽，不能证明所有输入乘区、敌人机制或实际游戏一致。详见 `.local/evidence/D008/event-checks.json`。','',
        '## 阻断高精度的事项','',
        '首个场景的敌人技能／阶段／特殊减伤仍是骨架；默认等级、精英组覆盖与关卡要求不一致；抗性导入不足；角色 caveats 尚未核验。所有问题按 `manifests/simulator-gaps.json` 分配到后续责任任务。','',
        'D035／D036 封装和预检时必须拒绝缺关键机制的精确请求，不能让本轮近似脚本成为默认完整模拟接口。D038 补齐首个场景，D042 核对事件与游戏控制样例后，才授予该场景精度资格；失败则回到 D008 重新选型。','',
        '## 复核命令','',
        '```powershell',
        "& '.local/probes/hsr-nous/中文 空格验证/Scripts/python.exe' -X utf8 tools/p0/run_core_tests.py",
        "& '.local/probes/hsr-nous/中文 空格验证/Scripts/python.exe' -X utf8 tools/p0/run_simulations.py",
        "& '.local/probes/hsr-nous/中文 空格验证/Scripts/python.exe' -X utf8 tools/p0/check_simulation_events.py",
        '```','',
        '安装／依赖日志、输入 YAML、各次输出、事件与耗时都在 `.local/evidence/D008/`；所有第三方游戏原始数据未放入共享 fixture。']
    dest=ROOT/'docs/feasibility/simulator-probe.md'
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    update_task('D008','DONE',summary='202 项相关回归通过；AV 预算补丁；两队各两次真实执行与复放一致；高精度缺口已登记',
        artifacts=['docs/feasibility/simulator-probe.md','manifests/simulator-gaps.json','patches/hsr-nous/0001-bound-av-with-pending-waves.patch'],
        commands=['python tools/p0/prepare_runtime.py','python tools/p0/start_simulator_probe.py',
                  'python tools/p0/capture_simulations.py','<隔离 Python> tools/p0/check_simulation_events.py'],
        counts={'passed':202,'failed':0,'skipped':0,'deselected':1,
                'deselected_reason':'optional FastAPI presentation layer excluded from core environment','live_team_runs':4,
                'independent_formula_checks':2,'event_checks':8},
        evidence=['.local/evidence/D008/core-tests.json','.local/evidence/D008/core-tests.xml',
            '.local/evidence/D008/simulation-summary.json','.local/evidence/D008/event-checks.json'],
        next_step='D009，按用户最终宿主范围作选型关口',level='上游真实执行／离线回归／历史公式与事件抽查；无全场游戏精度认证')
    print(json.dumps({'core_passed':202,'deselected':1,'team_runs':4,'game_accuracy_certified':False}))


if __name__=='__main__':
    main()
