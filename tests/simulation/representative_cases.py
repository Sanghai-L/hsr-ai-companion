from copy import deepcopy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def case(short="moc"):
    return json.loads((ROOT / f"benchmarks/modes/{short}/representative-v1.json").read_bytes())


def multi_case(mode="memory_of_chaos"):
    request = case("aa" if mode == "anomaly_arbitration" else "moc")
    pools = [["1002", "1001", "1105", "1104"], ["1013", "1211", "1203", "1301"], ["1312", "1107", "1221", "1109"]]
    candidates = []
    for i, pool in enumerate(pools):
        team = deepcopy(request["candidates"][0])
        team["id"] = "pool-" + str(i)
        for member, char_id in zip(team["members"], pool):
            member.update(character_id=char_id, form_id=char_id + ":base", rotation=["basic"])
        candidates.append(team)
    slots = []
    count = 3 if mode == "anomaly_arbitration" else 2
    for i in range(count):
        value = deepcopy(request)
        value["candidates"] = [deepcopy(candidates[i]), deepcopy(candidates[(i+1) % len(pools)])]
        slots.append({"id": "slot-" + str(i), "stage_type": "knight" if count == 3 else "side", "request": value})
    return {"mode": mode, "roster": {"origin": "explicit_hypothesis", "notes": "测试明确假设12名角色可用，无装备触发效果，不代表玩家持有",
        "available_character_ids": [item for pool in pools for item in pool], "available_equipment_instances": []},
        "slots": slots, "max_combinations": 256, "max_seconds": 10}
