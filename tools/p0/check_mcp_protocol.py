"""Exercise real stdio subprocesses, UTF-8, errors, EOF closure and restart."""
import json
import os
import subprocess
import time

from common import ROOT, LOCAL, now, write_json


def run(messages):
    python=LOCAL/'probes/mcp/中文 空格验证/Scripts/python.exe'
    env=os.environ.copy()
    env.update(PYTHONUTF8='1',PYTHONIOENCODING='utf-8')
    process=subprocess.Popen([python,ROOT/'tools/p0/mcp_probe.py'],
        stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
        encoding='utf-8',cwd=LOCAL/'probes/hosts/codex/中文 空格项目',env=env)
    start=time.perf_counter()
    text='\n'.join(m if isinstance(m,str) else json.dumps(m,ensure_ascii=False) for m in messages)+'\n'
    try:
        stdout,stderr=process.communicate(text,timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate()
        raise AssertionError('MCP probe did not exit after input EOF')
    assert process.returncode==0 and not stderr,(process.returncode,stderr)
    responses=[json.loads(line) for line in stdout.splitlines()]
    return {'pid':process.pid,'exit_code':process.returncode,'seconds':time.perf_counter()-start,
            'responses':responses,'eof_closed':True}


def main():
    req=lambda method,i=None,params=None:{'jsonrpc':'2.0','method':method,
        **({'id':i} if i is not None else {}),**({'params':params} if params is not None else {})}
    init=req('initialize',1,{'protocolVersion':'2025-11-25','capabilities':{},'clientInfo':{'name':'p0-wire-check','version':'1'}})
    notification=req('notifications/initialized')
    first=run([req('tools/list',0),init,notification,req('tools/list',2),
        req('tools/call',3,{'name':'probe_status','arguments':{}}),
        req('tools/call',4,{'name':'probe_status','arguments':{'uid':'not-an-account'}}),
        req('no_such_method',5),req('ping',6),'malformed{'])
    replies={r['id']:r for r in first['responses']}
    assert len(first['responses'])==8
    assert replies[0]['error']['code']==-32002
    assert replies[1]['result']['protocolVersion']=='2025-11-25'
    assert [t['name'] for t in replies[2]['result']['tools']]==['probe_status']
    fixed=json.loads(replies[3]['result']['content'][0]['text'])
    assert fixed=={'version':'0.1.0-p0','text':'星穹铁道 P0 探针可用'}
    assert replies[4]['error']['code']==-32602
    assert replies[5]['error']['code']==-32601
    assert replies[6]['result']=={}
    assert replies[None]['error']['code']==-32700
    second=run([init,notification,req('tools/call',3,{'name':'probe_status','arguments':{}})])
    assert first['pid']!=second['pid']
    assert second['responses'][-1]['result']==replies[3]['result']
    report={'at':now(),'checks_passed':10,'failures':0,'skips':0,'runs':[first,second],
        'layer':'real subprocess stdio protocol; distinct from actual Agent tests'}
    write_json(LOCAL/'evidence/D005/protocol-validation.json',report)
    print(json.dumps({'protocol_checks':10,'fresh_processes':2,'eof_closed':True}))


if __name__=='__main__':
    main()
