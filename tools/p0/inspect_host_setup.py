"""Read-only selected host status; never print or persist credential values."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tomllib

from common import LOCAL, now, write_json


if __name__=="__main__":
    codex=shutil.which('codex')
    result=subprocess.run([codex,'login','status'],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=20)
    # Intentionally do not log raw status text; some versions include key hints.
    output=result.stdout+'\n'+result.stderr
    login='LOGGED_IN' if 'Logged in' in output else 'NOT_LOGGED_IN' if 'Not logged in' in output else 'UNKNOWN'
    path=Path.home()/'.codex/config.toml'
    selection={}
    if path.exists():
        config=tomllib.loads(path.read_text(encoding='utf-8-sig'))
        selection={key:config.get(key) for key in ('model','model_provider','model_reasoning_effort')}
    status={'at':now(),'codex':{'login_status':login,'status_exit_code':result.returncode,
            'model_selection':selection},'dsh':{'installed_version':'0.2.1-rc.3','desktop_version':'44.7.0',
            'existing_profile_names':[p.name for p in (Path.home()/'.dsh/profiles').iterdir() if p.is_dir()]}}
    write_json(LOCAL/'evidence/D005/host-setup-status.json',status)
    print(json.dumps(status,ensure_ascii=False))
