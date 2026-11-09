"""Independent arithmetic/event checks, with explicit limits on game accuracy."""
import json
import math
from functools import reduce
from operator import mul
from common import ROOT, LOCAL, now, write_json


def main():
    from hsr_nous.sim.pipeline import SettlementPipeline, MODE_EXPECTED
    from hsr_nous.sim.state import ActorState
    from hsr_nous.sim_schema.actor import Actor, StatBlock
    from hsr_nous.sim_schema.action import Action
    # Historical published game-observation example; not a current-team accuracy test.
    source=Actor(actor_id="formula_observation",name="公式测试员",level=50,
        stats=StatBlock(atk=1062,hp=10000,spd=100,crit_rate=0,crit_dmg=0.5,
                        dmg_bonus={"thunder":0.258,"basic_dmg_boost":0.1}))
    target=Actor(actor_id="formula_target",name="公式假人",actor_type="monster",level=50,
        stats=StatBlock(hp=1e6,def_=700,spd=100,max_toughness=60))
    action=Action(action_id="historical_basic",name="独立公式普攻",action_type="basic",
                  target_type="single",damage_type="thunder",scaling=[{"atk":0.6}])
    pipeline=SettlementPipeline(mode=MODE_EXPECTED,seed=42)
    caster=ActorState(actor=source,current_hp=source.stats.hp)
    victim=ActorState(actor=target,current_hp=target.stats.hp)
    formula_checks=[]
    for broken in (False,True):
        victim.broken=broken
        result=pipeline.settle_damage("direct",caster,victim,action=action,skill_level=1)
        manual=(0.6*1062)*(1+0.258+0.1)*(1-700/(700+200+10*50))*0.8*(1 if broken else 0.9)
        assert math.isclose(result.value,manual,rel_tol=1e-12),(result.value,manual,result.node)
        formula_checks.append({"broken":broken,"independent_formula":manual,"backend":result.value,
            "published_displayed_value":346 if broken else 312,"matches_display_after_rounding":round(result.value)==(346 if broken else 312)})
    event_checks=[]
    for team_id in ("team-a","team-b"):
        run=json.loads((LOCAL/f"evidence/D008/{team_id}-run-1.json").read_text(encoding="utf-8"))
        # Independently multiply the reported factors for two actual damage events.
        for i,sample in enumerate(run["damage_samples"][:2]):
            factors={k:v for k,v in sample["node"].items() if k.endswith("Multi")}
            product=reduce(mul,factors.values(),1.0)
            assert math.isclose(product,sample["value"],rel_tol=1e-12),(product,sample)
            event_checks.append({"team":team_id,"damage_event":i,"value":sample["value"],
                "independent_factor_product":product,"scope":"trace arithmetic only, not independent verification of each input multiplier"})
        changes=[e for e in run['events'] if e['event_type']=='action']
        assert changes and all(0<=e['skill_points_after']<=5 for e in changes)
        event_checks.append({"team":team_id,"sp_events_checked":len(changes),"sp_bounds_valid":True})
    run=json.loads((LOCAL/"evidence/D008/team-a-run-1.json").read_text(encoding="utf-8"))
    enemies=json.loads((LOCAL/"evidence/D008/enemy-template-audit.json").read_text(encoding="utf-8"))
    for position,enemy in enumerate(enemies[:2]):
        actor_id=f"w0_{position}_{enemy['id']}"
        first=next(e for e in run['events'] if e['event_type']=='turn_start' and e['actor_id']==actor_id)
        expected=10000/enemy['base_stats']['spd']
        assert abs(first['timestamp']-expected)<=0.051
        event_checks.append({"actor":actor_id,"first_turn_av":first['timestamp'],"independent_10000_div_speed":expected,
                             "scope":"within approximate input stats only"})
    report={"at":now(),"source":"https://www.prydwen.gg/star-rail/guides/damage-formula",
        "source_level":"published historical game screenshots and arithmetic; not new game observations",
        "formula_checks":formula_checks,"event_checks":event_checks,
        "whole_scenario_accuracy_verified":False,"exit_code":0}
    write_json(LOCAL/"evidence/D008/event-checks.json",report)
    print(json.dumps({"formula_cases":len(formula_checks),"actual_event_checks":len(event_checks),"exit_code":0}))


if __name__=="__main__":
    main()
