"""Summarize D006 using observed schema and original synthetic fault fixtures."""
import json
from common import ROOT, LOCAL, now, write_json, update_task


def main():
    observation = json.loads((LOCAL/"evidence/D006/field-observation.json").read_text(encoding="utf-8"))
    raw = json.loads((LOCAL/"evidence/D006/public-example.raw.json").read_text(encoding="utf-8"))
    assert observation["http_status"] == 200
    fixture_dir = ROOT / "tests/fixtures/uid"
    example = {"detailInfo": {"nickname": "合成展示账号", "level": 70,
        "avatarDetailList": [{"avatarId": 1001, "level": 80, "promotion": 6, "rank": 0,
            "equipment": {"tid": 20000, "level": 80, "promotion": 6, "rank": 1},
            "relicList": [], "skillTreeList": []}]}, "ttl":60, "region":"synthetic"}
    fixtures = {
        "partial": {"synthetic":True, "http_status":200, "body":example,
                    "expected": {"showcase_count":1, "roster_complete":False, "ownership_unlisted":"unknown"}},
        "empty": {"synthetic":True, "http_status":200, "body":{"detailInfo":{"nickname":"合成空展示"},"ttl":60},
                  "expected":{"showcase_count":0,"full_roster":"unknown","reason":"closed_or_empty_not_distinguishable"}},
        "missing-field": {"synthetic":True, "http_status":200, "body":{"detailInfo":{"avatarDetailList":[{"avatarId":1001}]},"ttl":60},
                          "expected":{"level":None,"rank":None,"missing_fields":["level","rank","equipment","relicList","skillTreeList"]}},
        "schema-change": {"synthetic":True, "http_status":200, "body":{"profile_v2":{"characters":[]},"ttl":60},
                          "expected":{"error":"schema_changed","preserve_previous":True}},
        "rate-limit": {"synthetic":True,"http_status":429,"headers":{"Retry-After":"60"},"body":{},
                       "expected":{"error":"rate_limited","preserve_previous":True,"automatic_refresh":False}},
        "maintenance": {"synthetic":True,"http_status":424,"body":{},
                        "expected":{"error":"maintenance","preserve_previous":True}},
        "invalid-uid": {"synthetic":True,"http_status":400,"body":{},
                        "expected":{"error":"invalid_input","retryable":False}},
        "not-found": {"synthetic":True,"http_status":404,"body":{},
                      "expected":{"error":"not_found","preserve_previous":True}},
    }
    for name, fixture in fixtures.items():
        write_json(fixture_dir/(name+".json"),fixture)
    (fixture_dir/"README.md").write_text(
        "# UID 边界样本\n\n所有共享 JSON 均为原创合成数据，不含真实 UID、昵称、签名或个人配装。\n"
        "字段结构根据 D006 实际响应与源码核查整理，不是下载响应的副本。\n"
        "partial/empty/missing-field/schema-change 检查信息边界；其余 HTTP 故障纯合成，不对服务压测。\n"
        "expected 是后续 D024 的验收合同，本轮没有实现账号导入器，不声称这些业务测试已通过。\n",encoding="utf-8")
    region = raw.get("region")
    lines = ["# 公开 UID 字段矩阵", "", f"核验：{now()}。对 wrapper 作者自己文档与测试使用的同一个 HSR 公开例子只请求一次，HTTP 200，展示 {observation['showcase_character_count']} 人。", "",
        "该公开账号不是用户账号；原 UID、URL 和原始响应只保存在 `.local/evidence/D006/`。共享 fixture 全部重新构造为合成数据。", "",
        "| 项目 | 真实可得／边界 | 证据 |", "|---|---|---|",
        "| 入口 | `https://enka.network/api/hsr/uid/{uid}`；无 Cookie、无登录；可识别 User-Agent | 锁定 enka-py constants/common.py + 真实 200 |",
        f"| 区服 | 此次 response.region={region!r}，仅验证文档中的亚洲样例；其他区服未实测 | 原响应 + 字段观察 |",
        "| 玩家概况 | detailInfo 含等级及展示概况；不把个人信息写进共享文档 | 原响应字段键 |",
        "| 角色 | detailInfo.avatarDetailList 的 avatarId、enhancedId、level、promotion、rank；只代表公开展示 | 原响应 |",
        "| 光锥／遗器／行迹 | equipment、relicList、skillTreeList 可见；仅限展示角色已装备内容，不是背包 | 原响应 |",
        "| 完整面板 | 本次没有直接提供全部最终数值的面板字段；须结合等级、装备与版本数据推算，标注派生口径 | 观察到的 avatar keys |",
        "| 精度 | 输入等级／星魂等为整数；遗器词条值可能需版本数据解码，不能从显示字段推断隐藏小数速度 | 原响应结构；尚未做游戏比对 |",
        f"| 缓存 | 本次 ttl={observation['ttl']} 秒；是响应值，不写死服务全局 TTL | 真实响应 + [官方缓存与限流说明](https://github.com/EnkaNetwork/API-docs/blob/b94bc40528941126590e0eefb0f03278e7a44ec8/api.md) |",
        "| 限流 | 动态限流；本次不触发 429；Retry-After 与故障仅用合成数据 | 官方说明 |",
        "| 完整持有、背包、星琼、抽卡保底 | 不提供；未展示≠未持有；无推测补全 | 原响应字段范围 |",
        "| 空展示／缺字段 | 无法仅凭空列表区分隐藏与未设置；未知保持 null | 官方 Showcase 边界 + 合成样本 |", "",
        "TTL 到期只表示服务缓存可刷新，不授权本项目自动查询 UID。后续仍只接受玩家明确导入／刷新请求。未启用 wrapper 自带备用服务回退，避免扩大数据传输目的地。",
        "", "观察字段摘要：`.local/evidence/D006/field-observation.json`；请求意图、时间、状态和响应哈希在 request.json；真实响应不分发。",
        "", "样例授权依据：[库作者文档](https://github.com/seriaati/enka-py/blob/51380ff810139657b15518dfe98bc3d341a8d08d/docs/profile.md) 中显式给出的 HSR 示例，并由该仓库测试使用；没有扫描 UID。"]
    (ROOT/"docs/data/uid-field-matrix.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    update_task("D006","DONE",summary="文档指定公开样例单次 HTTP 200；字段与 TTL 实录；8 个原创合成边界样本",
        artifacts=["docs/data/uid-field-matrix.md","tests/fixtures/uid/"],commands=["python tools/p0/probe_uid.py","python tools/p0/finalize_uid.py"],
        counts={"passed":1,"failed":0,"skipped":0},evidence=[".local/evidence/D006/request.json",".local/evidence/D006/field-observation.json"],
        next_step="D009 待宿主与模拟验证完成",level="真实公开 UID 接口；故障场景为合成，尚非业务导入测试")
    print(json.dumps({"live_requests":1,"synthetic_fixtures":len(fixtures),"http_status":200}))


if __name__=="__main__":
    main()
