"""Regression for a real upstream failure: pending waves ignored the AV budget."""
import pytest
from hsr_nous.sim import CombatEngine, MODE_EXPECTED
from hsr_nous.sim_schema.actor import Actor, StatBlock
from hsr_nous.sim_schema.action import Action
from hsr_nous.sim_schema.encounter import Encounter, TerminationConfig


@pytest.mark.parametrize("mode",["fixed_av","survival","wipe"])
def test_pending_wave_cannot_disable_global_action_budget(mode):
    hero=Actor(actor_id="budget_hero",name="预算测试员",level=80,
               stats=StatBlock(hp=100000,atk=1,spd=100,max_energy=100))
    enemy=Actor(actor_id="budget_enemy",name="预算假人",actor_type="monster",level=80,
                stats=StatBlock(hp=1e9,spd=100))
    next_enemy=Actor(actor_id="next_enemy",name="下一波假人",actor_type="monster",level=80,
                    stats=StatBlock(hp=1e9,spd=100))
    action=Action(action_id="budget_basic",name="测试普攻",action_type="basic",
                  target_type="single",damage_type="physical",scaling=[{"atk":1.0}])
    encounter=Encounter(encounter_id="budget",name="预算回归",actors=[hero,enemy],
                        termination=TerminationConfig(mode=mode,max_action_value=150))
    engine=CombatEngine(encounter,actions_by_actor={"budget_hero":[action]},mode=MODE_EXPECTED,
                        initial_energy_ratio=0,wave_enemies={1:[next_enemy]})
    state=engine.run()
    assert state.clock <= 150, "A still-pending second wave must not disable the explicit budget"
    assert not state.truncated, "An AV budget must terminate before the emergency 200-turn cap"
    assert engine.current_wave == 0
