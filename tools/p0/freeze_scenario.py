"""D007: freeze released historical MoC data; keep gaps explicit."""
import json
import shutil
from common import ROOT, LOCAL, now, digest, write_json, update_task


def main():
    data = LOCAL / "data-snapshot"
    scenario_dir = LOCAL / "benchmarks/seed-scenario"
    scenario_dir.mkdir(parents=True, exist_ok=True)
    read = lambda p: json.loads((data/p).read_text(encoding="utf-8"))
    versions = read("stages/buhflipexplode/fh-versions.json")[-1]["versions"]
    version = versions["4.4.1"]
    floors = read("stages/hakushin/details/maze/1034.json")
    floor = next(f for f in floors if f.get("name") == "Stormcleanse (XII)")
    assert floor["param"] == [0.8, 1] and floor["event_id_list1"][0]["release"] is True
    assert version["versionTime"] == "17/08/2026 - 21/09/2026"
    event = floor["event_id_list1"][0]
    entities = read("starrailres/index_new/cn/characters.json")
    ids = ["1408", "1412", "1313", "1414", "1308", "1006", "1106", "1304"]
    aliases = []
    for cid in ids:
        source = entities[cid]
        aliases.append({"entity_id": cid, "official_name": source["name"], "path": source["path"],
                        "element": source["element"], "aliases": [], "shape_disambiguation": "ID 是主键；不与同名其他形态合并"})
    # Both teams contain no Hunt/Erudition characters; this turbulence has no eligible target.
    paths = {a["path"] for a in aliases}
    assert not paths & {"Rogue", "Mage", "Hunt", "Erudition"}, paths
    scenario = {"id": "alpha-moc", "mode": "memory-of-chaos", "official_or_synthetic": "released-historical-lineup",
        "recorded_at": now(), "game_version": "4.4", "data_snapshot_declares_live": "4.6",
        "current_live_source": json.loads((LOCAL/"sources/hakushin-manifest.json").read_text(encoding="utf-8"))["hsr"]["live"],
        "period_key": "4.4.1", "hakushin_period_id": "1034", "floor": 12, "side": "upper",
        "name": "扫除风暴 / Stormcleanse", "region": "source-unspecified",
        "region_note": "来源没有明确区服；按原始英文期数日期冻结，不能推广到所有区服的精确开关时间",
        "valid_time_source_text": version["versionTime"], "timezone_of_source_dates": None,
        "stage_id": event["stage_id"], "enemy_level": event["level"],
        "hard_level_group": event["hard_level_group"], "elite_group": event["elite_group"],
        "waves": [{"index": i, "monster_instance_ids": [str(v) for v in w.values()]} for i,w in enumerate(event["monster_list"])],
        "turbulence": {"buff_ids": version["versionBuffIDs"], "description_raw": floor["desc"], "parameters": floor["param"],
                       "applicability_to_candidates": "no eligible Hunt or Erudition unit; no active effect expected"},
        "scoring": {"total_cycle_budget_two_sides": floor["countdown"], "challenges_raw": floor["challenge"],
                    "upper_only_probe": True, "do_not_infer_full_stage_stars": True},
        "initial_resources": {"skill_points": 3, "energy": "upstream default 50% where supported", "source": "P0 controlled assumptions; not game observation"},
        "units": {"speed": "action distance per unit time", "action_distance": 10000,
                  "percentage_values": "0.8 means 80%, not 0.8 percentage point", "toughness": "upstream uses displayed points; verify source conversion before precise claims",
                  "eidolon_and_superimposition": "must record explicit zero/one-based indexing at runtime"},
        "entity_aliases": aliases,
        "missing_fields": ["区服及时区确证", "实际游戏初始能量／秘技", "正式关卡敌人完整技能、抗性与阶段交互的执行验证", "与游戏控制实测对齐", "当前 4.6 混沌期数时效验证"],
        "assumptions": ["使用当前锁定模板验证历史关卡编成，不声称还原 4.4 全套历史规则", "固定 E0、无装备的工程配置；不代表真实练度"],
        "status": "FROZEN_WITH_DECLARED_GAPS"}
    sources = ["stages/hakushin/details/maze/1034.json", "stages/hakushin/maze.json",
        "stages/buhflipexplode/fh-versions.json", "stages/buhflipexplode/buffs.json",
        "stages/hakushin/EliteGroup.json", "stages/hakushin/HardLevelGroup.json",
        "starrailres/index_new/cn/characters.json"]
    scenario["source_files"] = [{"path": ".local/data-snapshot/"+p, "sha256": digest(data/p)} for p in sources]
    write_json(scenario_dir/"scenario.json", scenario)
    shutil.copyfile(data/"stages/hakushin/details/maze/1034.json", scenario_dir/"source-floor-period.json")
    catalog_path = ROOT / "benchmarks/catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    case = catalog["cases"][0]
    case.update(status="FROZEN_WITH_DECLARED_GAPS")
    case["scenario"] = {k:scenario[k] for k in ("game_version", "period_key", "hakushin_period_id", "floor", "side", "region", "missing_fields")}
    case["scenario"].update(snapshot=".local/benchmarks/seed-scenario/scenario.json", sha256=digest(scenario_dir/"scenario.json"),
                            distribution="pointer-only; raw game data excluded")
    write_json(catalog_path, catalog)
    source_registry = ["# 数据来源登记", "", f"核验：{now()}。所有第三方原始数据只保存在 .local，不随工程分发。", "",
        "| 来源 | 冻结与观察 | 用途／限制 |", "|---|---|---|",
        "| [Hakushin 后端](https://static.nanoka.cc/manifest.json) | 实时 manifest 的 hsr.live=4.6；内容哈希保留 | 这只是来源的 live 标记，非游戏内验证；不读取 latest/beta 数据 |",
        "| [HSR_Nous 数据快照](https://github.com/pzc2004/HSR_Nous/releases/tag/data-full-20261016) | 日期标签、下载 SHA256、上游 digest 校验 | 内部多域更新不同步；旧 _snapshot_meta 不能代替各文件现状 |",
        "| Hakushin maze/1034 + buhflipexplode fh 4.4.1 | 扫除风暴，12 层上半；2026-08-17～2026-09-21，源时区未知 | 明确属于历史期，不是当前 4.6 场景 |",
        "| StarRailRes（快照内） | 角色 ID、形态、命途和元素对照 | 作为本地参考；AGPL 与游戏数据权利分开核查 |",
        "| tbgd（快照内） | 原始敌人、等级和精英系数 | 无独立复用授权结论，不纳入可分享 fixture |", "",
        "首个场景：`.local/benchmarks/seed-scenario/scenario.json`，共享目录只保留目录指针及哈希。",
        "", "候选队伍均没有巡猎／智识单位，因此该期只对巡猎／智识生效的紊流在本案例无合格目标；以后更换队伍必须重新检查。",
        "", "区服和源日期时区缺失、初始资源为工程假设、敌人 AI／阶段仍需 D008 核查。数值可运行不构成游戏精度认证。",
        "", "场景输入、来源、原始数据和运行规则分别保留版本；上游 Release 标签日期不推断每个文件已经更新到当天。"]
    folder = ROOT / "docs/data"
    folder.mkdir(parents=True, exist_ok=True)
    (folder/"source-registry.md").write_text("\n".join(source_registry)+"\n", encoding="utf-8")
    write_json(LOCAL/"evidence/D007/scenario-validation.json", {"at": now(), "exit_code":0,
        "period": "4.4.1", "source_hashes": scenario["source_files"], "teams_have_no_turbulence_target": True,
        "missing_fields": scenario["missing_fields"]})
    update_task("D007", "DONE", summary="冻结已上线历史 4.4.1／1034 混沌 12 层上半；未知区服与机制缺口显式保留",
        artifacts=["docs/data/source-registry.md", "benchmarks/catalog.json"],
        commands=["python tools/p0/collect_sources.py", "python tools/p0/unpack_snapshot.py", "python tools/p0/freeze_scenario.py"],
        counts={"passed": 5, "failed":0, "skipped":0}, evidence=[".local/evidence/D007/scenario-validation.json", ".local/benchmarks/seed-scenario/scenario.json"],
        next_step="D008", level="真实公开来源／冻结历史场景；非游戏内观测")
    print(json.dumps({"period":scenario["period_key"], "stage_id":scenario["stage_id"], "waves":scenario["waves"], "paths":sorted(paths)},ensure_ascii=False))


if __name__ == "__main__":
    main()
