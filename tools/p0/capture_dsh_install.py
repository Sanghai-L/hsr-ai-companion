import os
from common import ROOT, LOCAL, command

if __name__=="__main__":
    env=os.environ.copy()
    env['ELECTRON_RUN_AS_NODE']='1'
    result=command([r'E:\Deepseek Harness\DeepSeek Harness.exe',ROOT/'tools/p0/read_dsh_install.js'],
                    task='D005',name='dsh-install-static',env=env,timeout=20)
    print(result['stdout'][-2500:])
    print(result['stderr'][-1000:])
    raise SystemExit(result['exit_code'] if result['exit_code'] is not None else 4)
