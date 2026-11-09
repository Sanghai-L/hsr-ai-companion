"""Keep a reproducible two-line upstream repair and its license notice."""
import json
import shutil
from common import ROOT, LOCAL, command, digest, write_json, now

if __name__=="__main__":
    repo=LOCAL/"upstream/hsr-nous/repo"
    record=command(["git","diff","--","src/hsr_nous/sim/engine.py"],task="D008",name="upstream-patch-diff",cwd=repo)
    if record['exit_code'] != 0 or not record['stdout']:
        raise RuntimeError("No verified repair diff")
    patch=ROOT/"patches/hsr-nous/0001-bound-av-with-pending-waves.patch"
    patch.parent.mkdir(parents=True,exist_ok=True)
    patch.write_text(record['stdout'],encoding="utf-8",newline="\n")
    notice=ROOT/"licenses/HSR_Nous-MIT.txt"
    notice.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(repo/"LICENSE",notice)
    manifest_path=ROOT/"manifests/upstreams.lock.json"
    manifest=json.loads(manifest_path.read_text(encoding="utf-8"))
    primary=next(x for x in manifest['upstreams'] if x['id']=='hsr-nous')
    primary['local_patches']=[{'path':patch.relative_to(ROOT).as_posix(),'sha256':digest(patch),
        'reason':'pending next wave disabled explicit AV budget in fixed_av/survival/wipe',
        'modified_files':['src/hsr_nous/sim/engine.py'],
        'regression':'tests/p0/test_simulator_budget.py','license_notice':'licenses/HSR_Nous-MIT.txt'}]
    write_json(manifest_path,manifest)
    evidence=LOCAL/"evidence/D008"
    rejected=evidence/"initial-truncated"
    rejected.mkdir(exist_ok=True)
    for name in ('team-a-run-1.json','team-a-run-2.json','team-b-run-1.json','team-b-run-2.json','simulation-summary.json'):
        path=evidence/name
        if path.exists() and not (rejected/name).exists():
            shutil.copyfile(path,rejected/name)
    print(json.dumps({'patch_sha256':digest(patch),'original_results_preserved':str(rejected.relative_to(ROOT))}))
