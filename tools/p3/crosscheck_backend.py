"""Run actual locked backend expressions in its existing isolated runtime."""
import json
import subprocess
import sys

from companion.calculators.damage import calculate
from record import ROOT, now, write_json

PROGRAM = r'''
import json,sys
from hsr_nous.sim_schema.rulebook import get_rulebook
from hsr_nous.sim_schema.expression import evaluate
rb=get_rulebook()
values=[]
for p in json.load(sys.stdin):
    c={"attacker_level":p["attacker_level"],"target_def":10*p["enemy_level"]+200,
       "def_pen":p["def_reduction"]+p["def_ignore"],"target_res":p["resistance"],"res_pen":p["res_penetration"],
       "vulnerability":p["vulnerability"],"crit_rate":p["crit_rate"],"crit_dmg":p["crit_damage"],
       "target_broken":int(p["broken"]),"all_dmg_bonus":p["damage_bonus"],"elemental_dmg_bonus":0,"type_dmg_bonus":0}
    names={"damage_bonus":"dmg_boost_multi","defense":"def_multi","resistance":"res_multi","vulnerability":"vuln_multi",
           "crit":"crit_expected_multi","toughness":"base_universal_multi"}
    zones={k:evaluate(rb.zones[v],context=c,trace=False).value for k,v in names.items()}
    total=(p["stat"]["value"]+p["stat"]["equipment_bonus"])*p["multiplier"]+p["flat_damage"]
    for value in zones.values(): total*=value
    values.append({"value":total,"zones":zones})
print(json.dumps(values))
'''


def main():
    base = json.loads((ROOT / "tests/fixtures/requests/damage.json").read_bytes())["experiment"]["parameters"]
    samples = []
    for update in ({}, {"def_reduction": .4, "def_ignore": .1}, {"def_reduction": 1.2}, {"resistance": -.2},
                   {"crit_rate": 1}, {"crit_rate": 0}, {"broken": True}, {"attacker_level": 70, "enemy_level": 95}):
        samples.append({**base, **update})
    interpreter = ROOT / ".local/probes/hsr-nous/中文 空格验证/Scripts/python.exe"
    process = subprocess.run([str(interpreter), "-c", PROGRAM],input=json.dumps(samples),capture_output=True,text=True,encoding="utf-8",timeout=30)
    write_json(".local/evidence/D030/backend-expression-process.json", {"at":now(),"interpreter":str(interpreter),"exit_code":process.returncode,"stdout":process.stdout,"stderr":process.stderr})
    if process.returncode:
        raise RuntimeError(process.stderr)
    remote = json.loads(process.stdout)
    records = []
    for sample, result in zip(samples, remote):
        local = calculate(sample)
        assert abs(result["value"] - local["value"]) <= 1e-9
        for key, value in result["zones"].items():
            assert abs(value-local["zones"][key]) <= 1e-12
        records.append({"input":sample,"backend":result,"local":local,"absolute_error":abs(result["value"]-local["value"])})
    write_json(".local/evidence/D030/backend-crosscheck.json", {"at":now(),"status":"PASS","samples":records,
        "upstream_commit":"f8935ddb407b297732fbd3c624d55897e3e648b9", "scope":"actual expression evaluation in locked backend runtime; not independent game-client calibration",
        "intentional_difference":"local critical rate lower clamp at zero; backend expression lacks lower clamp, so negative crit rates excluded from agreement scope",
        "unsupported_extremes":"local effective resistance outside [-1,.9] rejected instead of claiming backend clamp game accuracy"})
    print(json.dumps({"status":"PASS","samples":len(records),"max_absolute_error":max(r["absolute_error"] for r in records)}))


if __name__ == "__main__":
    main()
