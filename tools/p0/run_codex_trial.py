"""Bounded fresh-session acceptance using the user's existing Codex login."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

from common import ROOT, LOCAL, now, write_json


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--phase',choices=['1','1r','2'],required=True)
    args=parser.parse_args()
    phase=args.phase
    folder=LOCAL/'evidence/D005/codex'
    folder.mkdir(parents=True,exist_ok=True)
    evidence=folder/f'fresh-{phase}.json'
    if evidence.exists():
        raise RuntimeError('Refusing to repeat a model trial automatically; inspect previous evidence first')
    setup=json.loads((LOCAL/'evidence/D005/host-setup-status.json').read_text(encoding='utf-8'))
    if setup['codex']['login_status']!='LOGGED_IN':
        raise RuntimeError('No existing Codex login; no credential collection or new login attempted')
    workspace=LOCAL/'probes/hosts/codex/中文 空格项目'
    python=LOCAL/'probes/mcp/中文 空格验证/Scripts/python.exe'
    prompt=('你好，介绍一下这个项目，用一句中文回答。' if phase in {'1','1r'} else
            '请搜索 MCP 官方 stdio 文档，再打开 https://modelcontextprotocol.io/specification/2025-11-25/basic/transports ，用一句中文说明找到的内容。')
    selection=setup['codex']['model_selection']
    command=[shutil.which('codex'),'exec','--ignore-user-config','--ephemeral','--skip-git-repo-check',
        '--sandbox','read-only','--json','-C',str(workspace),'-o',str(folder/f'fresh-{phase}-answer.txt')]
    if selection.get('model'):
        command+=['--model',selection['model']]
    for value in (
        'web_search='+json.dumps('disabled' if phase in {'1','1r'} else 'live'),
        'mcp_servers.hsr_p0.command='+json.dumps(str(python)),
        'mcp_servers.hsr_p0.args=['+json.dumps(str(ROOT/'tools/p0/mcp_probe.py'))+']',
        'mcp_servers.hsr_p0.startup_timeout_sec=10',
        'mcp_servers.hsr_p0.tool_timeout_sec=10',
        'mcp_servers.hsr_p0.tools.probe_status.approval_mode="approve"',
    ):
        command+=['-c',value]
    if selection.get('model_reasoning_effort'):
        command+=['-c','model_reasoning_effort='+json.dumps(selection['model_reasoning_effort'])]
    command.append(prompt)
    # No CODEX_HOME override or auth copy: the CLI manages its existing login.
    env=os.environ.copy()
    env.update(PYTHONUTF8='1',PYTHONIOENCODING='utf-8')
    start=time.perf_counter()
    process=subprocess.Popen(command,cwd=workspace,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                             text=True,encoding='utf-8',errors='replace')
    timeout=False
    try:
        stdout,stderr=process.communicate(timeout=120)
    except subprocess.TimeoutExpired:
        timeout=True
        subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True)
        stdout,stderr=process.communicate(timeout=10)
    record={'at':now(),'args':command,'cwd':str(workspace),'pid':process.pid,'exit_code':process.returncode,
            'seconds':time.perf_counter()-start,'timeout':timeout,'stdout':stdout,'stderr':stderr,
            'validation_layer':'actual fresh Codex session; model requests expected by D005',
            'no_prompt_startup_keyword':True}
    write_json(evidence,record)
    print(json.dumps({'phase':phase,'exit_code':process.returncode,'seconds':record['seconds'],'timeout':timeout,
                     'output_tail':stdout[-4000:],'stderr_tail':stderr[-800:]},ensure_ascii=False))


if __name__=='__main__':
    main()
