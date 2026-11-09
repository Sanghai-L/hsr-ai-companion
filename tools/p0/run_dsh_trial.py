"""DSH fresh-session probe using a temporary launch overlay, no profile edits."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time

from common import ROOT, LOCAL, now, write_json


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--phase',choices=['1','2'],required=True)
    args=parser.parse_args()
    folder=LOCAL/'evidence/D005/dsh'
    folder.mkdir(parents=True,exist_ok=True)
    evidence=folder/f'fresh-{args.phase}.json'
    if evidence.exists():
        raise RuntimeError('Inspect existing trial evidence before any deliberate rerun')
    workspace=LOCAL/'probes/hosts/dsh/中文 空格项目'
    python=LOCAL/'probes/mcp/中文 空格验证/Scripts/python.exe'
    overlay=[{'insert':[{'id':'hsr-p0-mcp','name':'@deepseek-ai/dsh-mcp-client','config':{
        'serverName':'hsr_p0','transport':'stdio','command':str(python),'args':[str(ROOT/'tools/p0/mcp_probe.py')],
        'failOnStartupError':True,'startupTimeoutMs':10000}}]},
        {'id':'session-persistence-jsonl','config':{'root':str(folder/'sessions')}},
        {'id':'session-title-llm','disabled':True}, {'id':'otel','disabled':True},
        {'id':'session-telemetry-otel','disabled':True}]
    overlay_path=workspace/'trial.patch.yml'
    overlay_path.write_text(json.dumps(overlay,ensure_ascii=False,indent=2),encoding='utf-8')
    launcher=r'E:\Deepseek Harness\resources\runtime\cli\bin\dsh.cmd'
    prompt=('你好，介绍一下这个项目，用一句中文回答。' if args.phase=='1' else
        '请打开 https://modelcontextprotocol.io/specification/2025-11-25/basic/transports ，用一句中文说明本页描述的 stdio 通信方式。')
    cmd=[launcher,'headless','--patch',str(overlay_path),'--json',prompt]
    env=os.environ.copy()
    # Existing host selection/auth stays inside DSH. Do not print/copy credentials.
    env.update(PYTHONUTF8='1',PYTHONIOENCODING='utf-8')
    start=time.perf_counter()
    process=subprocess.Popen(cmd,cwd=workspace,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
        text=True,encoding='utf-8',errors='replace')
    timeout=False
    try:
        stdout,stderr=process.communicate(timeout=90)
    except subprocess.TimeoutExpired:
        timeout=True
        subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True)
        stdout,stderr=process.communicate(timeout=10)
    record={'at':now(),'args':cmd,'cwd':str(workspace),'pid':process.pid,'exit_code':process.returncode,
        'seconds':time.perf_counter()-start,'timeout':timeout,'stdout':stdout,'stderr':stderr,
        'scope':'P0 new headless test session only; no existing session/config edited',
        'no_prompt_startup_keyword':True}
    write_json(evidence,record)
    print(json.dumps({'phase':args.phase,'exit_code':process.returncode,'seconds':record['seconds'],
        'timeout':timeout,'stdout_tail':stdout[-4500:],'stderr_tail':stderr[-1500:]},ensure_ascii=False))


if __name__=='__main__':
    main()
