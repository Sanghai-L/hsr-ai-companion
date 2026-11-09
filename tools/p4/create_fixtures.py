"""Original fixtures describe the engineering baseline, never player facts."""
import json
from copy import deepcopy
from record import ROOT, write_json


def member(cid):
    return {"character_id": cid, "form_id": cid + ":base", "ownership": "unknown", "level": 80, "promotion": 6,
            "eidolon": 0, "skill_levels": {"basic": 6, "skill": 10, "ultimate": 10, "talent": 10},
            "trace_policy": "all_unlocked", "light_cone": None, "relics": [], "attributes": {},
            "source_refs": ["synthetic:P0-controlled-no-equipment-build"]}


def main():
    base = json.loads((ROOT / "tests/fixtures/requests/damage.json").read_bytes())["experiment"]
    base.update(kind="simulation", conditions={"game_version": "4.4", "mode": "memory-of-chaos", "investment": "synthetic",
                                               "notes": "历史4.4.1编成，当前锁定模板，无装备工程构筑；不代表玩家账号或游戏通关预测"},
                assumptions=["E0，80级满突破，全行迹，6/10/10/10，无装备；初始3SP及50%普通能量是工程条件"],
                source_refs=["benchmark:alpha-moc:4.4.1:1034:12:upper"])
    base["parameters"] = {"scenario_id": "alpha-moc", "build": {"origin": "synthetic", "snapshot_id": None,
                           "members": [member(cid) for cid in ("1408", "1412", "1313", "1414")], "assumptions": list(base["assumptions"])},
                          "initial_resources": {"skill_points": 3, "energy_ratio": .5, "techniques": [], "source_ref": "synthetic:P0-controlled-resources"},
                          "policy": {"id": "p0-bounded", "skill_threshold": 2, "support_target_form_id": "1408:base"},
                          "mode": "roll", "seed": 42, "precision": "model_diagnostic"}
    write_json("tests/fixtures/requests/simulation.json", {"experiment": base})
    write_json("src/companion/resources/examples/simulation.json", {"experiment": base})
    write_json("tests/fixtures/builds/team-a.json", base["parameters"]["build"])
    second = deepcopy(base["parameters"]["build"])
    second["members"] = [member(cid) for cid in ("1308", "1006", "1106", "1304")]
    write_json("tests/fixtures/builds/team-b.json", second)
    print("Prepared original two-team fixtures and public preflight example")


if __name__ == "__main__":
    main()
