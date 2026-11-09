"""D005: accept only the user-adjusted host scope and actual call evidence."""
import json
from common import ROOT, LOCAL, now, write_json, update_task


def events(record):
    return [json.loads(line) for line in record['stdout'].splitlines() if line.strip()]


def main():
    folder=LOCAL/'evidence/D005'
    protocol=json.loads((folder/'protocol-validation.json').read_text(encoding='utf-8'))
    accepted=[]
    for name in ('fresh-1r.json','fresh-2.json'):
        record=json.loads((folder/'codex'/name).read_text(encoding='utf-8'))
        stream=events(record)
        assert record['exit_code']==0 and not record['timeout']
        calls=[e['item'] for e in stream if e['type']=='item.completed'
               and e.get('item',{}).get('type')=='mcp_tool_call'
               and e['item'].get('tool')=='probe_status' and e['item'].get('status')=='completed']
        assert len(calls)==1 and calls[0]['error'] is None
        result=json.loads(calls[0]['result']['content'][0]['text'])
        assert result=={'version':'0.1.0-p0','text':'星穹铁道 P0 探针可用'}
        messages=[e['item']['text'] for e in stream if e['type']=='item.completed' and e.get('item',{}).get('type')=='agent_message']
        assert any('STAR-RAIL-P0-RULE-20261106' in m for m in messages)
        webs=[e['item'] for e in stream if e['type']=='item.completed' and e.get('item',{}).get('type')=='web_search']
        accepted.append({'file':'.local/evidence/D005/codex/'+name,
            'thread_id':next(e['thread_id'] for e in stream if e['type']=='thread.started'),
            'mcp_calls_completed':len(calls),'rule_marker_observed':True,'exit_code':0,
            'web_actions':[w.get('action',{}) for w in webs],
            'usage':next(e['usage'] for e in stream if e['type']=='turn.completed')})
    assert accepted[0]['thread_id']!=accepted[1]['thread_id']
    second=events(json.loads((folder/'codex/fresh-2.json').read_text(encoding='utf-8')))
    web=[e['item'] for e in second if e['type']=='item.completed' and e.get('item',{}).get('type')=='web_search']
    searches=[w for w in web if w.get('action',{}).get('type') in {'search','search_query'}]
    fetches=[w for w in web if w.get('action',{}).get('type')=='open_page']
    assert searches and any(w.get('results') for w in searches),[w.get('action') for w in web]
    assert fetches and any(w.get('results') for w in fetches)
    dsh=json.loads((folder/'dsh/fresh-1.json').read_text(encoding='utf-8'))
    assert 'MISSING_CREDENTIAL' in dsh['stdout'] and dsh['exit_code']==1
    baseline=json.loads((LOCAL/'evidence/D002/environment.json').read_text(encoding='utf-8'))
    manifest={'schema_version':1,'at':now(),'p0_scope':'codex only by explicit user steering',
        'hosts':[
            {'id':'codex','version':baseline['tools']['codex']['version'],'status':'P0_VALIDATED',
             'rules':'isolated AGENTS.md auto-discovery','mcp':'stdio; session-specific CLI config',
             'fresh_sessions':2,'search_verified':True,'fetch_verified':True,'evidence':accepted},
            {'id':'dsh','cli_version':'0.2.1-rc.3','desktop_version':'44.7.0','status':'USER_DEFERRED',
             'startup_checked':True,'mcp_plugin_startup_checked':True,'agent_tool_call_verified':False,
             'model_error':'MISSING_CREDENTIAL for deepseek-official','search_verified':False,'fetch_verified':False},
            {'id':'claude-code','status':'USER_DEFERRED','actual_call_verified':False}],
        'stdio_protocol_checks':protocol['checks_passed'],
        'player_confirmation_contract':'not implemented in P0; business confirmation belongs to D017/D018',
        'user_config_modified':False}
    write_json(ROOT/'manifests/hosts.lock.json',manifest)
    lines=['# Agent 兼容性矩阵','',f'核验：{now()}。本轮用户先暂缓 Claude Code，再明确暂缓 DSH 验收；本轮 P0 关口只计 Codex。','',
        '| 宿主 | 实际版本 | 本轮结果 |','|---|---|---|',
        '| Codex | 0.166.0-alpha.5.1 | 两个独立新会话均实际调用 probe_status、返回规则标记；第二次独立完成搜索与指定 URL 获取 |',
        '| DSH | CLI 0.2.1-rc.3；桌面 44.7.0 | 本机入口、帮助与 MCP 插件启动已检验；默认 headless 模型 MISSING_CREDENTIAL，用户明确暂缓；未通过真实工具调用／联网验收 |',
        '| Claude Code | 未实测 | 用户明确暂缓；没有创建适配或宣称支持 |','',
        '## Codex 的已测路径','',
        '工作区：`.local/probes/hosts/codex/中文 空格项目/`。规则来自其中的 AGENTS.md；测试提示为普通问候，未在提示里提到工具名、规则标记或启动口令。第二个进程重新建立了独立会话。',
        '',
        'MCP 通过 CLI `-c mcp_servers.hsr_p0.*` 作为本次会话配置；只对这个固定文本探针指定 `tools.probe_status.approval_mode="approve"`。宿主命令使用 read-only 沙箱、ephemeral 会话和已有登录，不修改全局配置。',
        '',
        '首轮工具因非交互 approval=never 被拒；修正只读工具声明和该工具专属配置后复测成功。最初的未知 projects 配置参数已移除。失败与修正记录均保留。',
        '',
        '项目 `.codex/config.toml` 是官方支持的配置位置，但信任与安装流程要在 D018 做正式验收。本轮采用已实测的会话参数，不把未测的持久信任流程算作通过。',
        '',
        '参考：[官方 MCP 配置](https://learn.chatgpt.com/docs/extend/mcp)、[官方项目规则发现](https://learn.chatgpt.com/docs/agent-configuration/agents-md)。',
        '',
        '## 搜索和 URL 获取分别验收','',
        '- 搜索：真实 Codex 轨迹含 search 操作和返回来源，查询 MCP 官方 stdio 文档。',
        '- 获取：同一会话随后独立执行 open_page，取得指定传输规范页面。',
        '- 使用 Codex 已有宿主能力，不新增搜索付费服务；这不构成所有用户免费套餐的可用性承诺。',
        '- DSH 的默认搜索实现会发出辅助模型请求，并需要 DEEPSEEK_API_KEY；本轮未调用。HTTP fetch 与 search 是分开的能力，未用前者冒充后者。',
        '',
        '## 进程与权限','',
        '独立协议验证包含初始化、发现、只读调用、非法参数、未知方法、坏 JSON、UTF-8 与两个新进程。输入 EOF 后服务器正常退出，无独立后台服务。宿主试验都有超时，超时时只清理本次创建的 PID 树。',
        '',
        'P0 的批准仅覆盖固定文本探针；没有完成玩家确认／冲突修改等业务授权框架。P1 的 D017/D018 必须实现并验证业务确认传递，不能复用本探针的专属免问配置到写入工具。',
        '',
        'DSH 通过独立 `--patch` 启动参数接入探针；既有配置和会话不改写。它能进入真实新会话，但因默认模型凭据缺失而未运行工具；该失败明确保留。',
        '',
        '脱敏版本与验收摘要：`manifests/hosts.lock.json`。完整命令与轨迹：`.local/evidence/D005/`。']
    (ROOT/'docs/compatibility/agent-matrix.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    update_task('D005','DONE',summary='按用户最终范围完成 Codex 两次真实新会话；搜索/获取独立成功；DSH、Claude 明确暂缓',
        artifacts=['docs/compatibility/agent-matrix.md','manifests/hosts.lock.json','tools/p0/mcp_probe.py'],
        commands=['python tools/p0/check_mcp_protocol.py','python tools/p0/run_codex_trial.py --phase 1r',
                  'python tools/p0/run_codex_trial.py --phase 2','python tools/p0/run_dsh_trial.py --phase 1','python tools/p0/finalize_hosts.py'],
        counts={'passed':10,'failed':0,'skipped':0,'actual_codex_sessions':2,'search_checks':1,'fetch_checks':1,
                'historical_rejected_probe_attempts':1,'dsh_failed_trial_user_deferred':1,
                'user_deferred_hosts':['dsh','claude-code']},
        evidence=['.local/evidence/D005/protocol-validation.json','.local/evidence/D005/codex/fresh-1r.json',
                  '.local/evidence/D005/codex/fresh-2.json','.local/evidence/D005/dsh/fresh-1.json'],
        next_step='D009',level='实际 Codex Agent／原生网页能力；DSH 未通过且用户暂缓')
    print(json.dumps({'codex_sessions':2,'search':True,'fetch':True,'scope':'codex only; dsh/claude user-deferred'}))


if __name__=='__main__':
    main()
