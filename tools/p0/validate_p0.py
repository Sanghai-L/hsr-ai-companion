"""Offline P0 acceptance checks; never installs, queries accounts, or calls models."""
import argparse
import ast
import json
from pathlib import Path
import re
import sys

from common import ROOT, LOCAL, now, digest, write_json, command


def read(path):
    return json.loads((ROOT/path).read_text(encoding='utf-8'))


def validate(*,shared_only=False,require_gate=True):
    checks=[]
    def checked(name,condition,detail=''):
        if not condition:
            raise ValueError(name+(': '+detail if detail else ''))
        checks.append({'name':name,'passed':True,'detail':detail})
    baseline=read('docs/requirements/baseline.json')
    checked('PRD copy hash',digest(ROOT/baseline['prd'])==baseline['sha256'])
    checked('Original plans unchanged',all(digest(ROOT/name)==sha for name,sha in baseline['planning_hashes'].items()))
    tasks=read('docs/development/task-status.json')['tasks']
    checked('58 unique sequential tasks',[t['id'] for t in tasks]==[f'D{i:03}' for i in range(1,59)])
    ledger=(ROOT/'docs/development/task-status.md').read_text(encoding='utf-8')
    checked('58 ledger rows exactly once',re.findall(r'^\| (D\d{3}) \|',ledger,re.M)==[t['id'] for t in tasks])
    checked('P0 task status',all(t['status']=='DONE' for t in tasks[:(9 if require_gate else 8)]))
    checked('Later task states and completed dependencies',all(
        t['status'] in {'NOT_STARTED','IN_PROGRESS','BLOCKED','DONE'} and
        (t['status'] != 'DONE' or all(next(item for item in tasks if item['id']==dep)['status']=='DONE' for dep in t['dependencies']))
        for t in tasks[9:]))
    trace=(ROOT/'docs/requirements/traceability.md').read_text(encoding='utf-8')
    # Later stage evidence tables legitimately refer to the same acceptance IDs.
    # Validate uniqueness in the owning registry, not in all historical mentions.
    owner_table=trace.split('| 验收 | 需求 |',1)[1].split('\n\n',1)[0]
    checked('All 24 acceptance owners',re.findall(r'^\| (A\d{2}) \|',owner_table,re.M)==[f'A{i:02}' for i in range(1,25)])
    for task in tasks[:(9 if require_gate else 8)]:
        checked(task['id']+' completion record',bool(task['completed_at'] and task['snapshot'] and task['commands'] and task['evidence']))
    cases=read('evals/cases/seed-12.json')['cases']
    checked('12 distinct seed questions',len(cases)==12 and len({q['id'] for q in cases})==12)
    checked('Seed observables',all(q['necessary_facts'] and q['capabilities'] and q['forbidden_behaviors'] and q['pass_conditions'] for q in cases))
    accounts=[read('tests/fixtures/accounts/synthetic-'+name+'.json') for name in ('a','b')]
    checked('Two synthetic isolated accounts',len({a['account_id'] for a in accounts})==2 and all(a['synthetic'] and a['uid'] is None for a in accounts))
    checked('Unknown ownership retained',all(a['ownership_of_unlisted']=='unknown' and a['roster_completeness']=='partial' for a in accounts))
    checked('Zero distinct from unknown',accounts[1]['resources']['stellar_jade']=={'value':0,'status':'known','source':'synthetic-manual'}
            and accounts[1]['resources']['special_passes']['value'] is None and accounts[1]['resources']['special_passes']['status']=='unknown')
    fixtures=list((ROOT/'tests/fixtures/uid').glob('*.json'))
    checked('8 synthetic UID boundary fixtures',len(fixtures)==8 and all(json.loads(p.read_text(encoding='utf-8'))['synthetic'] is True for p in fixtures))
    def contains_real_uid(value):
        if isinstance(value,dict):
            return any((key.lower()=='uid' and item is not None and re.fullmatch(r'\d{9,10}',str(item))) or contains_real_uid(item) for key,item in value.items())
        return isinstance(value,list) and any(contains_real_uid(item) for item in value)
    checked('No real UID in shared fixtures',all(not contains_real_uid(json.loads(p.read_text(encoding='utf-8'))) for p in (ROOT/'tests/fixtures').rglob('*.json')))
    upstreams=read('manifests/upstreams.lock.json')['upstreams']
    checked('8 full upstream commit pins',len(upstreams)==8 and all(re.fullmatch('[0-9a-f]{40}',u['commit']) for u in upstreams))
    checked('License decisions recorded',all(u.get('distribution_decision') and 'redistribution_approved' in u for u in upstreams))
    primary=next(u for u in upstreams if u['id']=='hsr-nous')
    checked('Repair and notice hashes',all(digest(ROOT/p['path'])==p['sha256'] and (ROOT/p['license_notice']).exists() for p in primary['local_patches']))
    checked('No premature project license',not (ROOT/'LICENSE').exists())
    deps=(ROOT/'tools/p0/simulator-requirements.lock').read_text(encoding='utf-8')
    checked('Dependencies versioned and hashed','pyyaml==6.0.3' in deps and 'pytest==' in deps and deps.count('--hash=sha256:')>=8)
    hosts=read('manifests/hosts.lock.json')
    codex=next(h for h in hosts['hosts'] if h['id']=='codex')
    checked('Codex two actual sessions',codex['status']=='P0_VALIDATED' and codex['fresh_sessions']==2
            and len({e['thread_id'] for e in codex['evidence']})==2)
    checked('Search and fetch independently verified',codex['search_verified'] and codex['fetch_verified'])
    checked('Explicit user host deferrals',all(h['status']=='USER_DEFERRED' for h in hosts['hosts'] if h['id'] in {'dsh','claude-code'}))
    gaps=read('manifests/simulator-gaps.json')
    checked('Precision limits not erased',gaps['game_accuracy_certified'] is False and all(g['owners'] for g in gaps['gaps']) and any(g['blocks_precise_results'] for g in gaps['gaps']))
    catalog=read('benchmarks/catalog.json')['cases']
    checked('Historical scenario with explicit missing fields',len(catalog)==1 and catalog[0]['id']=='alpha-moc'
            and catalog[0]['scenario']['period_key']=='4.4.1' and bool(catalog[0]['scenario']['missing_fields']))
    checked('Two runnable four-person approximate teams',all(len(t['candidate_entity_ids'])==4 and t['runnable'] and t['replay_identical'] and t['strict_scenario_supported'] is False for t in catalog[0]['teams']))
    checked('Private data ignored','.local/' in (ROOT/'.gitignore').read_text(encoding='utf-8'))
    for path in (ROOT/'tools/p0').glob('*.py'):
        ast.parse(path.read_text(encoding='utf-8'),filename=str(path))
    checked('All P0 Python scripts parse',True)
    if not shared_only:
        origin=read('.local/evidence/D001/requirements-origin.json')
        original=Path(origin['source'])
        checked('Original PRD still matches',original.exists() and digest(original)==baseline['sha256'])
        checked('Downloaded source hashes',all(digest(ROOT/f['path'])==f['sha256'] for u in upstreams for f in u['files'] if f['status']==200))
        tools=read('manifests/probe-tools.lock.json')
        checked('uv binary and archive match pin',digest(LOCAL/'tools/uv/uv.exe')==tools['uv']['executable_sha256']
                and digest(LOCAL/'tools/uv/uv.zip')==tools['uv']['archive_sha256'])
        checked('Frozen scenario hash',digest(ROOT/catalog[0]['scenario']['snapshot'])==catalog[0]['scenario']['sha256'])
        scenario=read(catalog[0]['scenario']['snapshot'])
        checked('Scenario source hashes',all(digest(ROOT/f['path'])==f['sha256'] for f in scenario['source_files']))
        protocol=read('.local/evidence/D005/protocol-validation.json')
        checked('Protocol evidence and EOF closure',protocol['checks_passed']==10 and all(r['exit_code']==0 and r['eof_closed'] for r in protocol['runs']))
        request=read('.local/evidence/D006/request.json')
        checked('One real documented public UID query',request['request_count']==1 and request['http_status']==200
                and digest(LOCAL/'evidence/D006/public-example.raw.json')==request['raw_sha256'])
        core=read('.local/evidence/D008/core-tests.json')
        checked('202 core tests with explained exclusion',core['exit_code']==0 and '202 passed, 1 deselected' in core['stdout'])
        runs=read('.local/evidence/D008/simulation-summary.json')['teams']
        checked('All four real simulation runs accepted',len(runs)==2 and all(r['runnable'] and r['replay_identical'] and not r['truncated'] for r in runs))
        for team in runs:
            pair=[read(f".local/evidence/D008/{team['id']}-run-{i}.json") for i in (1,2)]
            checked(team['id']+' full replay',pair[0]['model_replay_sha256']==pair[1]['model_replay_sha256']
                    and pair[0]['events']==pair[1]['events'] and pair[0]['log']==pair[1]['log'])
        event=read('.local/evidence/D008/event-checks.json')
        checked('Independent formula and event evidence',event['exit_code']==0 and len(event['formula_checks'])==2 and len(event['event_checks'])==8)
        repair=command(['git','apply','--reverse','--check',ROOT/primary['local_patches'][0]['path']],
                        task='D009',name='installed-patch-check',cwd=LOCAL/'upstream/hsr-nous/repo')
        checked('Installed repair matches distributable patch',repair['exit_code']==0,repair['stderr'])
    if require_gate:
        gate=read('docs/gates/P0.json')
        checked('Gate uses user-adjusted scope',gate['status']=='PASS_USER_ADJUSTED_SCOPE' and gate['host_scope']==['codex']
                and gate['original_three_host_requirement_met'] is False and gate['whole_game_accuracy_verified'] is False)
    return {'at':now(),'mode':'shared-only' if shared_only else 'local-evidence',
            'checks':checks,'passed':len(checks),'failed':0,'exit_code':0}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--shared-only',action='store_true',help='Check shareable artifacts without local private evidence')
    args=parser.parse_args()
    try:
        report=validate(shared_only=args.shared_only)
    except (ValueError,FileNotFoundError,KeyError,AssertionError) as exc:
        print(json.dumps({'status':'incomplete-or-invalid','error':str(exc)},ensure_ascii=False))
        raise SystemExit(3)
    write_json(LOCAL/'evidence/D009'/('validation-shared.json' if args.shared_only else 'validation.json'),report)
    print(json.dumps({'status':'passed','checks':report['passed'],'mode':report['mode']}))


if __name__=='__main__':
    main()
