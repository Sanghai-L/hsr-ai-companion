"""Original synthetic fixtures; hand answers are literal independent values."""
from copy import deepcopy
from companion import __version__
from record import write_json


def experiment(kind, parameters, *, source="synthetic:p3-independent-hand-calculation"):
    return {"schema_version": 1, "kind": kind,
            "conditions": {"game_version": "4.6", "mode": "local-analysis", "investment": "synthetic", "notes": "原创合成基准，非真实账号或当前卡池"},
            "versions": {"engine": __version__, "rules": "p3-1", "knowledge": "0.2.0", "data": "p3-fixtures-1"},
            "budget": {"max_events": 100, "max_av": 1000, "max_transitions": 3000000, "max_seconds": 10},
            "parameters": parameters, "assumptions": ["所有输入均为明确的合成条件，不代表实际角色整场表现"], "source_refs": [source]}


def main():
    damage = experiment("damage", {"damage_type": "direct", "stat": {"value": 1000, "unit": "flat", "basis": "public_panel", "equipment_bonus": 0},
        "multiplier": 2, "flat_damage": 0, "attacker_level": 80, "enemy_level": 80,
        "damage_bonus": .5, "def_reduction": 0, "def_ignore": 0, "resistance": .2, "res_penetration": 0,
        "vulnerability": .25, "crit_rate": .5, "crit_damage": 1, "crit_mode": "expected", "broken": False})
    write_json("tests/fixtures/requests/damage.json", {"experiment": damage})
    write_json("benchmarks/formulas/damage.json", {"id": "p3-damage-hand-1", "experiment": damage, "expected": 2025,
        "derivation": "1000*2 * 1.5 * 100/(100+100) * 0.8 * 1.25 * (1+0.5*1) * 0.9 = 2025",
        "zone_expected": {"base_damage": 2000, "damage_bonus": 1.5, "defense": .5, "resistance": .8, "vulnerability": 1.25, "crit": 1.5, "toughness": .9},
        "independence": "answer specified using rational arithmetic, without invoking the implementation or simulator"})
    action = {"kind": "basic", "sp_cost": 0, "sp_gain": 1, "energy_gain": 20, "regen_applies": True, "effects": []}
    actor = {"id": "A", "speed": 100, "energy": 0, "energy_cap": 100, "energy_regen": 0, "rotation": [action]}
    timeline = experiment("timeline", {"actors": [actor], "sp": 0, "sp_cap": 5, "until_av": 175,
        "scheduled": [{"at": 50, "actor": "A", "kind": "speed", "value": 200}]})
    write_json("tests/fixtures/requests/timeline.json", {"experiment": timeline})
    write_json("benchmarks/formulas/timeline.json", {"id": "p3-speed-hand-1", "experiment": timeline, "normal_turn_av": [75, 125, 175],
        "derivation": "at AV50, remaining gauge=10000-100*50=5000; change to SPD200; first turn=50+5000/200=75; subsequent interval=10000/200=50"})
    rules = {"id": "toy-half-then-guarantee", "pool_type": "synthetic", "hard_pity": 2, "featured_rate": 1,
             "hazards": [.5, 1], "curve_kind": "synthetic", "source_refs": ["synthetic:exhaustive-two-pull-tree"], "note": "仅验证算法，不代表游戏卡池"}
    state = {"pool_type": "synthetic", "pity": 0, "guaranteed": False}
    gacha = experiment("gacha", {"rules": rules, "state": state, "pulls": 1, "copies": 1})
    write_json("tests/fixtures/requests/gacha.json", {"experiment": gacha})
    write_json("benchmarks/formulas/gacha.json", {"id": "p3-probability-tree-1", "experiment": gacha,
        "first_hit_distribution": [0, .5, .5], "success_probability": .5, "expected_pulls_to_target": 1.5,
        "derivation": "first success probability 1/2; only failure branch (1/2) must succeed at pull 2; expectation=1/2+2/2"})
    zero = {"jade": 0, "tickets": 0}
    benefit = {"kind": "qualitative", "description": "合成目标，无战斗收益数据；只比较可达性"}
    plan = experiment("pull_plan", {"as_of": "2026-11-08", "budget": {"jade": 160, "tickets": 0}, "reserve_pulls": 0,
        "income": [{"id": "single-original-event", "available_on": "2026-11-09", "source_ref": "synthetic:one-time-income",
                    "conservative": zero, "neutral": {"jade": 0, "tickets": 1}, "optimistic": {"jade": 160, "tickets": 1}}],
        "states": [state], "preferences": ["先保留现实预算上限，不充值"],
        "options": [{"id": "new-character", "category": "new_character", "stages": [{"id": "first", "deadline": "2026-11-09",
                    "schedule_status": "hypothetical", "rules": rules, "copies": 1}], "benefit": benefit,
                    "reversal_conditions": ["偏好转向保留资源，或真实目标价值不足时选择不抽"]},
                   {"id": "two-targets", "category": "team_completion", "stages": [{"id": "first", "deadline": "2026-11-09",
                    "schedule_status": "hypothetical", "rules": rules, "copies": 1}, {"id": "second", "deadline": "2026-11-09",
                    "schedule_status": "hypothetical", "rules": rules, "copies": 1}], "benefit": benefit,
                    "reversal_conditions": ["两目标共享预算不足时，优先只选一个目标或不抽"]}]})
    write_json("tests/fixtures/requests/pull-plan.json", {"experiment": plan})
    for name, value in (("damage", damage), ("timeline", timeline), ("gacha", gacha), ("pull-plan", plan)):
        write_json(f"src/companion/resources/examples/{name}.json", {"experiment": value})
    write_json("evals/cases/pull-plans.json", {"id": "p3-original-pull-plan-cases-1", "cases": [
        {"id": "one-target-three-incomes", "request": "tests/fixtures/requests/pull-plan.json", "option": "new-character", "expected_probabilities": [.5, 1, 1]},
        {"id": "two-targets-shared-budget", "option": "two-targets", "expected_probabilities": [0, .25, .75], "proof": "costs 1/2 with probability .5 each; sum distribution: 2=.25, 3=.5, 4=.25"},
        {"id": "unknown-future-banner", "expect": "missing_schedule; no invented date"},
        {"id": "duplicate-income", "expect": "INVALID_INPUT"},
        {"id": "unknown-pity", "expect": "no guessed starting state"},
        {"id": "no-comparable-battle-benefit", "expect": "ranking=null; qualitative explanation; skip included"}]})
    print("Created original P3 request fixtures and independent benchmarks")


if __name__ == "__main__":
    main()
