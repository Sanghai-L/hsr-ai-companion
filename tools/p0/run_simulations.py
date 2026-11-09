"""D008 two-team probe. Outputs are engineering approximations, never advice."""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import traceback

import yaml

from common import ROOT, LOCAL, now, write_json, digest


def offline_guard(event, args):
    if event in {"socket.connect", "socket.getaddrinfo", "subprocess.Popen", "os.system"}:
        raise RuntimeError("Simulator probe forbids external calls/processes: " + event)


def run_one(compiled, team_id, run_index, folder):
    from hsr_nous.sim import CombatEngine, MODE_ROLL
    from hsr_nous.sim.structured_log import StructuredLogger
    engine = CombatEngine.from_compiled(compiled, mode=MODE_ROLL, seed=42,
                                       initial_sp=3, initial_energy_ratio=0.5)
    logger = StructuredLogger(engine)
    samples = []
    original = engine.pipeline.settle_damage
    def observe_damage(*args, **kwargs):
        result = original(*args, **kwargs)
        if len(samples) < 3:
            samples.append(asdict(result))
        return result
    engine.pipeline.settle_damage = observe_damage
    start = time.perf_counter()
    state = engine.run()
    seconds = time.perf_counter()-start
    snapshot = state.snapshot()
    # Use full structured events and logs, not just rounded total damage.
    deterministic = {"snapshot": snapshot, "events": logger.entries, "log": state.log, "damage_samples": samples}
    canonical = json.dumps(deterministic,ensure_ascii=False,sort_keys=True,separators=(",",":"))
    output = {"team_id":team_id,"run":run_index,"seed":42,"mode":"roll", "seconds":seconds,
        "validation_scope":"approximate engineering execution; not a faithful MoC game result",
        "strict_scenario_supported":False, "model_replay_sha256":hashlib.sha256(canonical.encode()).hexdigest(),
        "caveats":list(compiled.caveats), **deterministic}
    write_json(folder/f"{team_id}-run-{run_index}.json",output)
    return output


def main():
    os.environ["HSR_NOUS_DATA_DIR"] = str(LOCAL/"data-snapshot")
    from hsr_nous.sim.compile import compile_encounter
    from hsr_nous.sim_schema.rulebook import get_rulebook
    from hsr_nous.adapters.template_generator import generate_enemy_template
    from hsr_nous.pipeline.enemies.loader import get_enemy_detail
    sys.addaudithook(offline_guard)
    folder = LOCAL/"evidence/D008"
    scenario = json.loads((LOCAL/"benchmarks/seed-scenario/scenario.json").read_text(encoding="utf-8"))
    templates = LOCAL/"probes/simulation-templates"
    (templates/"enemies").mkdir(parents=True,exist_ok=True)
    metadata = []
    waves = []
    for wave in scenario["waves"]:
        members=[]
        for position,eid in enumerate(wave["monster_instance_ids"]):
            tpl = generate_enemy_template(eid,level=scenario["enemy_level"],data_dir=str(LOCAL/"data-snapshot"))
            dest = templates/"enemies"/(eid+"_probe.yaml")
            dest.write_text(yaml.safe_dump(tpl,allow_unicode=True,sort_keys=False),encoding="utf-8")
            detail = get_enemy_detail(eid,tbgd_dir=str(LOCAL/"data-snapshot/turnbasedgamedata"))
            metadata.append({"id":eid,"name":tpl["name"],"level":tpl["level"],"base_stats":tpl["base_stats"],
                "weakness":tpl["weakness"],"notes":tpl.get("notes",[]),
                "instance_hard_level_group":detail.get("HardLevelGroup"),"instance_elite_group":detail.get("EliteGroup"),
                "scenario_hard_level_group":scenario["hard_level_group"],"scenario_elite_group":scenario["elite_group"],
                "stat_groups_match_scenario":detail.get("HardLevelGroup")==scenario["hard_level_group"] and detail.get("EliteGroup")==scenario["elite_group"],
                "complete_enemy_mechanics":False})
            members.append({"enemy_template":eid,"actor_id":f"w{wave['index']}_{position}_{eid}","level":scenario["enemy_level"]})
        waves.append(members)
    modes=get_rulebook().modes
    mode=next((k for k in ("forgotten_hall","moc","memory_of_chaos","fh") if k in modes),None)
    if mode is None:
        raise ValueError("Cannot identify MoC rulebook mode from "+str(list(modes)))
    stage={"stage":{"stage_id":"alpha-moc-4.4.1-12-upper-APPROX","mode":mode,
        "enemies":waves[0],"waves":[{"wave_index":i,"enemies":w} for i,w in enumerate(waves) if i],
        "termination":{"mode":"fixed_av","max_action_value":650}}}
    (folder/"stage-input.yaml").write_text(yaml.safe_dump(stage,allow_unicode=True,sort_keys=False),encoding="utf-8")
    write_json(folder/"enemy-template-audit.json",metadata)
    roots=[str(LOCAL/"upstream/hsr-nous/repo/data/library"),str(templates)]
    catalog=json.loads((ROOT/"benchmarks/catalog.json").read_text(encoding="utf-8"))
    results=[]
    for team in catalog["cases"][0]["teams"]:
        build={"build":{"team":[{"character_template":cid,"level":80,"eidolon":0} for cid in team["candidate_entity_ids"]],
            "policy":{"name":"p0-bounded-rule-policy","action_rules":[
                {"condition":"energy >= max_energy","action":"ultimate","priority":90},
                {"condition":"skill_points > 2","action":"skill","priority":50},
                {"condition":"true","action":"basic","priority":0}],
                "target_rules":([{ "condition":"true","selector":{"type":"has_modifier","modifier_id":"TRACE_1408103"}}] if team['id']=='team-a' else []),
                "parameters":{}}}}
        (folder/(team['id']+"-input.yaml")).write_text(yaml.safe_dump(build,allow_unicode=True,sort_keys=False),encoding="utf-8")
        try:
            compiled=compile_encounter(build,stage,template_roots=roots)
            outputs=[run_one(compiled,team['id'],i,folder) for i in (1,2)]
            identical=outputs[0]["model_replay_sha256"]==outputs[1]["model_replay_sha256"]
            result={"id":team['id'],"runnable":True,"replay_identical":identical,
                "damage":outputs[0]['snapshot']['total_damage'],"turns":outputs[0]['snapshot']['turn_count'],
                "seconds":[r['seconds'] for r in outputs],"caveat_count":len(compiled.caveats),
                "truncated":outputs[0]['snapshot']['truncated'],"strict_scenario_supported":False}
            if not identical:
                raise AssertionError("Same-seed full event replay differed")
        except Exception as exc:
            result={"id":team['id'],"runnable":False,"error":str(exc),"traceback":traceback.format_exc()}
        results.append(result)
        print(json.dumps(result,ensure_ascii=False),flush=True)
    write_json(folder/"simulation-summary.json",{"at":now(),"teams":results,
        "source_scenario_sha256":digest(LOCAL/"benchmarks/seed-scenario/scenario.json"),
        "network_access":"forbidden by Python audit hook", "model_call_packages_installed":False,
        "known_gaps":["stage_template not implemented","enemy actions are placeholders without real damage/AI",
            "stage-specific elite/hard-level overrides must be checked","enemy resistance not imported by template path",
            "candidate-specific character caveats","no game observation validation"],
        "comparison_is_game_recommendation":False})
    raise SystemExit(0 if all(r['runnable'] and r['replay_identical'] for r in results) else 3)


if __name__=="__main__":
    main()
