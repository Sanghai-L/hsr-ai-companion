"""Maintainer-authored factual summaries and a retrieval set fixed before indexing.

This is a development tool, never exposed to player Agents or knowledge updates.
Raw source text stays in .local; distributed text is independently phrased.
"""
import hashlib
import json
from pathlib import Path
import sys

from record import ROOT, now, write_json

# id, category, title, aliases, source JSON keys, independently written claim, limitation
CONTENT = [
    ("damage-scaling", "battle", "伤害倍率的基准属性", ["攻击力", "防御力", "倍率", "砂金普攻"], ["130401", "140801"],
     "技能按其指定的属性计算。砂金普攻取防御力，白厄普攻取攻击力；不能把所有伤害都当成攻击力倍率。", "这只是技能文本口径，完整伤害乘区及舍入尚未核验。"),
    ("damage-tag", "battle", "动画、反击与伤害类型标签", ["反击", "战技伤害", "白厄反击", "动画"], ["140809"],
     "白厄变身后的特定反击在技能文本中被视为战技伤害。判断增益能否生效要看伤害标签，不能仅凭反击动画归为追加攻击。", "不能将这条特殊规定推广为所有角色的反击都算战技。"),
    ("skill-target", "battle", "成为技能目标与造成伤害不同", ["成为目标", "火种触发", "没有伤害", "队友技能"], ["140804"],
     "白厄的火种触发条件包含成为其他目标的技能目标，因此队友对他施放技能也可能触发，并不要求先对敌人造成伤害。", "须逐项核对技能目标与额外触发限制；本文没有验证所有多目标交互。"),
    ("action-advance", "battle", "立即行动与配速的适用条件", ["拉条", "行动提前", "配速", "星期日拉条"], ["131302"],
     "星期日战技可使指定角色及其召唤物立即行动；对同谐角色不触发立即行动。配速讨论需先确认目标是否满足条件。", "立即行动不等于提高速度；本条不提供行动值计算。"),
    ("shield-cap", "battle", "护盾叠加有技能限定的上限", ["叠盾", "无限盾", "护盾上限", "护盾叠加"], ["130402", "141402"],
     "砂金和丹恒·腾荒的技能允许同源护盾重复叠加，同时写明上限。能叠加不代表可以无限累积。", "不同来源护盾的结算规则不能由这两个技能直接推定。"),
    ("debuff-once", "battle", "一次技能的负面效果与多段命中", ["黄泉叠层", "多段", "每段", "残梦"], ["130804"],
     "黄泉天赋对施放技能期间使敌方陷入负面效果的触发设有每次技能至多一次的限制。多段伤害本身不能直接推出多层残梦。", "额外行动、装备效果和不同施放者需另查触发来源；不宣称一切叠层都受同一上限约束。"),
    ("weakness-resistance", "battle", "弱点植入与抗性降低分别判断", ["植入弱点", "银狼弱点", "减抗", "原有弱点"], ["100602"],
     "银狼战技的弱点植入、对应属性抗性降低和额外全属性抗性降低分别有条件。若添加原有属性弱点，文本规定不触发对应属性的抗性降低。", "不能把增加弱点理解为任意敌人对该属性都没有抗性。"),
    ("probability-label", "battle", "基础概率与固定概率不是同一标签", ["基础概率", "固定概率", "效果命中", "概率"], ["100602", "122408"],
     "银狼战技使用基础概率标签，巡猎三月七强化普攻追加段数使用固定概率标签。评估效果命中前应先区分概率种类。", "本阶段不提供命中公式，不把基础概率直接当作最终命中率。"),
    ("extra-turn", "battle", "白厄额外回合不能当成普通回合", ["额外回合", "回合", "卡厄斯兰那"], ["140803", "140805"],
     "白厄变身后不进入自己的普通回合，而以限定数量的额外回合行动，并有最后一击与致命伤害的特殊处理。", "普通回合计时和其他角色的增益消耗不能未经核验直接套用。"),
    ("buff-clock", "battle", "增益持续时间要找正确计时主体", ["增益回合", "持续回合", "蒙福者", "增益持续"], ["131303"],
     "星期日蒙福者的持续回合在星期日自己的回合开始时递减。比较覆盖率时，要记录计时主体而非只看持续几回合。", "其他增益可能按受益者或其他事件计时，不能全套用此规则。"),
    ("followup-hits", "battle", "一次追加攻击可以包含多段伤害", ["追击", "多段追加", "砂金七段", "追加攻击"], ["130404"],
     "砂金盲注达到阈值后发动一次包含多段随机目标伤害的追加攻击。攻击次数与命中段数是不同统计单位。", "多目标情况下的随机分配需要事件或模拟数据，不能假定全部打在同一目标。"),
    ("ignore-weakness", "battle", "无视弱点削韧是技能特例", ["无视弱点", "削韧", "黄泉终结技", "击破"], ["130803", "100607"],
     "黄泉终结技与银狼秘技存在无视弱点属性削韧的文本规定。应按具体技能范围判断，不能推广成队伍所有攻击都可无视弱点。", "削韧、弱点击破和伤害抗性是不同机制；本条不证明完整击破公式。"),
    ("phainon-fireseed", "characters", "白厄：火种与队友目标技能", ["白厄", "白恶", "火种", "1408"], ["140802", "140804"],
     "白厄战技可获得火种，天赋也会在他成为其他目标的技能目标时获得火种。队友技能的目标与施放频次是研究启动的关键条件。", "本条不声称任意队伍能在固定轮次变身；需给出队伍、技能和星魂。"),
    ("phainon-transform", "characters", "白厄：变身境界与队友离场", ["白厄变身", "卡厄斯兰那", "时墟铁墓", "1408"], ["140803", "140805"],
     "白厄终结技变身并展开境界，其他队友离场且无法行动，敌方始终具有物理弱点。变身拥有单独资源、额外回合和最后一击。", "队友离场期间的召唤物、计时与装备交互需要独立验证。"),
    ("cerydra-charge", "characters", "刻律德菈：军功、爵位与奇袭", ["刻律德菈", "刻律德拉", "军功", "奇袭", "1412"], ["141202", "141204"],
     "刻律德菈通过充能使军功升级为爵位；爵位受益者对敌人施放战技会触发奇袭。军功仅对最新目标生效，换目标会重置充能。", "奇袭期间不能按普通施放继续为刻律德菈充能；具体阈值按技能等级查询。"),
    ("sunday-advance", "characters", "星期日：角色和召唤物立即行动", ["星期日", "周日", "星期天", "拉条", "1313"], ["131302"],
     "星期日战技使目标角色及其召唤物立即行动，并提供增伤；对同谐角色无法触发立即行动。对蒙福者施放战技还会返还战技点。", "不能仅凭有召唤物便认定所有特殊单位都适用，需核对单位分类。"),
    ("sunday-energy", "characters", "星期日：恢复能量与蒙福者", ["星期日充能", "蒙福者", "周日大招", "1313"], ["131303"],
     "星期日终结技按目标能量上限恢复能量，并给予目标及其召唤物蒙福者增益；仅对最新施放目标生效。", "特殊资源不能未经证据当作普通能量；与白厄火种、黄泉残梦的交互另查。"),
    ("danheng-shield", "characters", "丹恒·腾荒：同袍与全队护盾", ["丹恒腾荒", "腾荒", "同袍", "1414"], ["141402", "141403"],
     "丹恒·腾荒战技指定同袍并提供全队护盾，盾值按自身攻击力计算；同袍仅保留最新战技目标。终结技也能提供护盾。", "不能把丹恒、饮月和腾荒视为同一战斗形态。"),
    ("danheng-dragon", "characters", "丹恒·腾荒：龙灵与强化行动", ["龙灵", "腾荒龙灵", "1414"], ["141403", "141404"],
     "同袍存在时丹恒·腾荒召唤龙灵。龙灵行动可解负面效果并提供护盾；终结技使它在限定行动次数内发动追加攻击。", "丹恒·腾荒或同袍无法战斗时龙灵消失；完整时序尚未游戏内核验。"),
    ("acheron-stacks", "characters", "黄泉：残梦、集真赤与负面效果", ["黄泉", "残梦", "集真赤", "1308"], ["130804"],
     "黄泉以残梦激活终结技，敌方被施加负面效果可触发天赋获取残梦与集真赤，文本含每次施放技能的触发次数限制。", "不是每段伤害都增加残梦，负面效果来源需逐项记录。"),
    ("acheron-ultimate", "characters", "黄泉：终结技削韧与阶段", ["黄泉大招", "黄泉终结技", "啼泽雨斩", "1308"], ["130803", "130814", "130817"],
     "黄泉终结技包括连续啼泽雨斩与黄泉返渡，期间消去集真赤并有无视弱点属性削韧的规定。不能只看一次动画段数推定触发次数。", "完整伤害、抗性降低和多目标结算要用具体技能等级及规则。"),
    ("silverwolf-implant", "characters", "银狼：弱点与缺陷的不同触发", ["银狼", "弱点植入", "缺陷", "1006"], ["100602", "100604"],
     "银狼战技可植入场上我方属性之一的弱点；天赋在攻击后按基础概率施加随机缺陷。植入弱点和天赋缺陷不能当成同一个效果。", "概率命中和弱点选择需要敌人已有弱点与队伍属性，资料缺失时不报必定结果。"),
    ("pela-dispel", "characters", "佩拉：解除增益与通解减防", ["佩拉", "解增益", "减防", "通解", "1106"], ["110602", "110603", "110604"],
     "佩拉战技能解除目标增益，终结技通过通解降低敌方防御；天赋在攻击有负面效果目标后额外回能，每次攻击限一次。", "可解除性由具体增益决定，不声称所有敌人增益都能被驱散。"),
    ("aventurine-followup", "characters", "砂金：坚垣筹码、盲注与追加攻击", ["砂金", "沙金", "盲注", "坚垣筹码", "1304"], ["130402", "130404"],
     "砂金为全队提供可叠加且有上限的坚垣筹码。持盾目标受击为他积累盲注，达到阈值后发动多段追加攻击。", "阈值和单次受击奖励要区分砂金自身与其他队友；不能把护盾当治疗。"),
    ("march-preservation", "characters", "三月七·存护：冰盾与反击", ["三月七", "三月七存护", "冰三月", "冰盾", "1001"], ["100102", "100104"],
     "存护形态三月七是冰属性角色，战技给单体护盾；持盾队友受攻击时可触发她的反击并受到每回合次数限制。", "这不是巡猎三月七；不共享技能或属性。"),
    ("march-hunt", "characters", "三月七·巡猎：师父与强化普攻", ["三月七", "巡猎三月", "三月七巡猎", "剑三月", "1224"], ["122402", "122404", "122408"],
     "巡猎形态三月七是虚数属性角色，通过师父行动获得充能并触发强化普攻；该强化普攻明确不能恢复战技点。", "不要把普通普攻常见的产点直觉套到这次强化普攻，也不要混入存护形态冰盾。"),
    ("forms", "basics", "同名角色的形态与实体 ID", ["同名形态", "角色形态", "丹恒", "三月七形态"], ["characters:1001", "characters:1224", "characters:1002", "characters:1213", "characters:1414"],
     "同名或同一人物的不同战斗形态使用不同实体 ID，例如三月七存护与巡猎、丹恒与饮月及腾荒。读取账号、技能和研究时应保留形态标识。", "拥有一个形态不能自动推断另一形态的练度与装备。"),
    ("paths", "basics", "命途描述定位，技能决定具体机制", ["命途", "存护", "同谐", "虚无"], ["characters:1304", "characters:1313", "characters:1308"],
     "角色数据把砂金、星期日和黄泉分别列为存护、同谐和虚无。命途可用于初步定位，但配队时仍需看角色的实际技能与条件。", "命途不保证伤害、辅助或生存能力可用统一强度排序。"),
    ("elements", "basics", "伤害属性与弱点判断", ["属性", "物理", "量子", "雷属性"], ["characters:1408", "characters:1006", "characters:1308"],
     "角色拥有标记的伤害属性：白厄物理、银狼量子、黄泉雷。敌方弱点、技能削韧特例与抗性需要另行读取。", "不能仅凭角色属性确定敌人的实际抗性或能否削韧。"),
    ("showcase", "basics", "公开展示不等于完整持有清单", ["UID", "展示", "未持有", "背包", "星琼", "保底"], ["enka:Showcase", "enka:ttl"],
     "Enka 的公开展示接口返回玩家展示的资料。未展示的角色与装备应保持未知；背包、完整持有、星琼和抽卡保底不能由展示推定。缓存 TTL 也不授权自动刷新。", "空展示不能单凭响应确定是隐藏还是未设置；账号只在明确导入或刷新时查询。"),
    ("skill-level", "basics", "技能等级与参数必须对应", ["技能等级", "倍率等级", "行迹", "叠影", "星魂"], ["130402", "131303"],
     "技能数据的描述占位符由等级参数表填充。谈护盾倍率或能量恢复时，应先记录技能等级，星魂与光锥叠影也不能当作同一个编号。", "本条不为未知练度补默认满级，也不保证任意参数可跨版本复用。"),
    ("technique", "basics", "秘技资源与战斗内技能有区别", ["秘技点", "秘技", "战技点", "开战"], ["140807", "141207", "122408"],
     "白厄秘技会使用秘技点并改变开战资源，刻律德菈秘技触发的开战战技不耗战技点；巡猎三月七强化普攻不产战技点。资源收支应按具体技能而非技能名称猜测。", "本阶段尚未实现战技点、能量时序计算器。"),
]

# Human-authored relevance labels. Holdout is fixed here before search implementation.
QUERIES = [
    ("白厄火种怎么攒", ["phainon-fireseed"]), ("白恶启动", ["phainon-fireseed"]),
    ("变身队友能行动吗", ["phainon-transform"]), ("刻律德拉奇袭", ["cerydra-charge"]),
    ("周日拉条召唤物", ["sunday-advance"]), ("星期日大招回能", ["sunday-energy"]),
    ("腾荒盾按什么属性", ["danheng-shield"]), ("龙灵什么时候消失", ["danheng-dragon"]),
    ("黄泉残梦", ["acheron-stacks"]), ("黄泉大招无视弱点吗", ["acheron-ultimate", "ignore-weakness"]),
    ("银狼弱点植入", ["silverwolf-implant"]), ("佩拉能解增益吗", ["pela-dispel"]),
    ("沙金追击", ["aventurine-followup", "followup-hits"]), ("三月七存护冰盾", ["march-preservation"]),
    ("巡猎三月师父", ["march-hunt"]), ("同名形态怎么区分", ["forms"]),
    ("命途决定机制吗", ["paths"]), ("角色属性与弱点", ["elements"]),
    ("UID不展示就是未持有吗", ["showcase"]), ("技能倍率要看等级吗", ["skill-level"]),
    ("秘技点与战技点", ["technique"]), ("砂金普攻是攻击倍率吗", ["damage-scaling"]),
    ("白厄反击算战技伤害", ["damage-tag"]), ("队友不造成伤害能给火种吗", ["skill-target"]),
    ("立即行动等于提高速度吗", ["action-advance"]), ("叠盾有上限吗", ["shield-cap"]),
    ("黄泉多段每段都加残梦吗", ["debuff-once"]), ("银狼原有弱点减抗", ["weakness-resistance"]),
    ("基础概率与固定概率", ["probability-label"]), ("白厄额外回合", ["extra-turn"]),
    ("蒙福者按谁的回合减少", ["buff-clock"]), ("砂金七段是七次追加吗", ["followup-hits"]),
    ("三月七不是巡猎是冰盾", ["march-preservation"]), ("白厄火种不需要敌人受伤", ["skill-target", "phainon-fireseed"]),
    ("星期日对同谐可以拉条吗", ["sunday-advance", "action-advance"]), ("丹恒腾荒龙灵强化", ["danheng-dragon"]),
    ("黄泉叠层一次技能限制", ["debuff-once", "acheron-stacks"]), ("军功换目标充能", ["cerydra-charge"]),
    ("剑三月强化普攻不恢复战技点", ["march-hunt"]), ("未公开的装备能认为没有吗", ["showcase"]),
    ("拉条不是加速", ["action-advance"]), ("沙金防御力影响护盾", ["aventurine-followup", "shield-cap"]),
]


def main():
    origins = json.loads((ROOT / ".local/evidence/D021/source-verification.json").read_bytes())["sources"]
    by_name = {Path(o["private_path"]).name: o for o in origins}
    stamp = max(o["observed_at"] for o in origins)
    skills = json.loads((ROOT / by_name["character_skills.json"]["private_path"]).read_bytes())
    characters = json.loads((ROOT / by_name["characters.json"]["private_path"]).read_bytes())
    registry = {"schema_version": 1, "version_scope": "4.6 frozen source snapshot; not a game-client certification",
                "sources": origins, "distribution": "original factual paraphrases; raw game/source content excluded; project license undecided"}
    for key, category, title, aliases, locators, text, exception in CONTENT:
        supports, refs = [], []
        for locator in locators:
            if locator.startswith("enka:"):
                source, pointer = by_name["enka-api.md"], locator.split(":", 1)[1]
            elif locator.startswith("characters:"):
                source, pointer = by_name["characters.json"], "/" + locator.split(":", 1)[1]
                assert pointer[1:] in characters
            else:
                source, pointer = by_name["character_skills.json"], "/" + locator + "/desc"
                assert locator in skills
            ref = source["url"] + "#" + pointer
            refs.append({"type": "web", "ref": ref, "observed_at": source["observed_at"], "license": "source rights reserved; facts paraphrased"})
            supports.append({"claim": text, "source_ref": ref, "locator": pointer, "source_sha256": source["sha256"],
                             "verification": "source_text_checked; game-client interaction not verified"})
        entities = (["1001:preservation"] if key == "march-preservation" else ["1224:hunt"] if key == "march-hunt" else [])
        entry = {"id": key, "category": category, "title": title, "aliases": aliases,
                 "version_min": "4.6", "version_max": "4.6", "information_state": "official_verified",
                 "evidence": "community", "body_path": f"{category}/{key}.md", "namespace": "release", "entities": entities,
                 "conditions": ["仅核对锁定 4.6 来源文本；不证明游戏内完整结算"], "exceptions": [exception],
                 "sources": refs, "claims": supports, "verified_at": stamp,
                 "license": "Original factual summary; project distribution license undecided; game rights reserved"}
        write_json(f"knowledge/{category}/{key}.json", entry)
        path = ROOT / f"knowledge/{category}/{key}.md"
        path.write_text(f"# {title}\n\n{text}\n\n适用范围：4.6 锁定资料；正式服文本核对，不等于游戏实测。\n\n例外与待核实：{exception}\n\n来源：\n" + "\n".join(f"- [{r['ref'].split('#')[-1]}]({r['ref']})" for r in refs) + "\n", encoding="utf-8")
    write_json("knowledge/sources.json", registry)
    dataset = {"schema_version": 1, "dataset_version": "p2-retrieval-1", "annotated_at": now(),
               "annotation_method": "maintainer manual relevance labels, fixed before index/search implementation",
               "queries": [{"id": f"q{i+1:02}", "query": query, "relevant_ids": relevant,
                            "split": "development" if i < 30 else "validation", "version": "4.6"}
                           for i, (query, relevant) in enumerate(QUERIES)]}
    query_file = ROOT / "evals/retrieval/queries.json"
    if query_file.exists():
        raise RuntimeError("retrieval labels already frozen; never silently regenerate")
    write_json("evals/retrieval/queries.json", dataset)
    write_json(".local/evidence/D022/query-set-frozen.json", {"at": now(), "sha256": hashlib.sha256(query_file.read_bytes()).hexdigest(),
               "development": 30, "validation": len(QUERIES)-30, "search_implementation_present": (ROOT / "src/companion/knowledge/search.py").exists()})
    print(f"Authored {len(CONTENT)} entries; froze {len(QUERIES)} queries")


if __name__ == "__main__":
    main()
