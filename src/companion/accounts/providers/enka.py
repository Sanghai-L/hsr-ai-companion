"""Public showcase only. No login, fallback service, inventory or derived panel."""
import hashlib
import json
import re

from companion.contracts import CompanionError, ErrorCode, canonical
from companion.sources.http import fetch


class EnkaProvider:
    def __init__(self, *, transport=fetch):
        self.transport = transport

    def query(self, uid):
        if not isinstance(uid, str) or not re.fullmatch(r"\d{9,10}", uid):
            raise CompanionError(ErrorCode.INVALID_INPUT, "UID 格式错误")
        response = self.transport(f"https://enka.network/api/hsr/uid/{uid}")
        if response.status != 200:
            code = ErrorCode.INVALID_INPUT if response.status == 400 else ErrorCode.MISSING_DATA if response.status in {404, 424} else ErrorCode.NETWORK_FAILURE
            raise CompanionError(code, "公开展示查询未成功；保留原账号资料", retryable=response.status in {429, 500, 503, 504},
                                 details={"http_status": response.status, "retry_after": response.headers.get("Retry-After")})
        try:
            payload = json.loads(response.body)
        except (ValueError, UnicodeError):
            raise CompanionError(ErrorCode.VERSION_INCOMPATIBLE, "UID 返回格式已变化")
        return payload, response.body


def normalize(payload, *, account_id, query_id, observed_at, region):
    if not isinstance(payload, dict) or not isinstance(payload.get("detailInfo"), dict):
        raise CompanionError(ErrorCode.VERSION_INCOMPATIBLE, "公开展示结构变化，缺少 detailInfo")
    ttl = payload.get("ttl")
    if type(ttl) is not int or not 0 <= ttl <= 604800:
        raise CompanionError(ErrorCode.VERSION_INCOMPATIBLE, "公开展示缓存时间未知或格式变化")
    avatars = payload["detailInfo"].get("avatarDetailList", [])
    if not isinstance(avatars, list) or len(avatars) > 30:
        raise CompanionError(ErrorCode.VERSION_INCOMPATIBLE, "展示角色列表格式变化")
    reported_region = payload.get("region")
    if reported_region in {"ASIA", "AMERICA", "EUROPE", "TW_HK_MO", "CN_OFFICIAL", "CN_CHANNEL"} and reported_region != region:
        raise CompanionError(ErrorCode.CONFLICT, "公开展示返回区服与账号配置不同")
    fields, characters, equipment, missing, seen = [], [], [], [], set()
    source = {"type": "uid_public", "ref": "uid-query:" + query_id, "observed_at": observed_at}

    def field(entity, name, value, maximum=1000000):
        if value is not None and (type(value) is not int or not 0 <= value <= maximum):
            raise CompanionError(ErrorCode.VERSION_INCOMPATIBLE, "展示字段数值类型或范围变化", details={"field": name})
        if value is None:
            missing.append(entity + "." + name)
        fields.append({"entity_id": entity, "field_id": name, "quantity": {"value": value, "unit": "count", "state": "unknown" if value is None else "known", "precision": None},
                       "source": source, "confirmed": False, "basis": "record"})

    for avatar in avatars:
        if not isinstance(avatar, dict) or type(avatar.get("avatarId")) is not int or avatar["avatarId"] <= 0:
            raise CompanionError(ErrorCode.VERSION_INCOMPATIBLE, "展示角色缺少合法 avatarId")
        cid = str(avatar["avatarId"])
        enhanced = avatar.get("enhancedId", 0)
        if type(enhanced) is not int or enhanced < 0:
            raise CompanionError(ErrorCode.VERSION_INCOMPATIBLE, "角色强化形态字段变化")
        form_id = f"{cid}:{enhanced or 'base'}"
        if form_id in seen:
            raise CompanionError(ErrorCode.VERSION_INCOMPATIBLE, "展示角色形态重复")
        seen.add(form_id)
        entity = "character:" + form_id
        characters.append({"character_id": cid, "form_id": form_id, "ownership": "owned"})
        for key, maximum in (("level", 80), ("promotion", 6), ("rank", 6)):
            field(entity, key, avatar.get(key), maximum)
        tree = avatar.get("skillTreeList")
        if tree is None:
            missing.append(entity + ".skillTreeList")
        elif not isinstance(tree, list) or len(tree) > 100:
            raise CompanionError(ErrorCode.VERSION_INCOMPATIBLE, "行迹字段变化")
        else:
            for point in tree:
                if not isinstance(point, dict) or type(point.get("pointId")) is not int:
                    raise CompanionError(ErrorCode.VERSION_INCOMPATIBLE, "行迹 ID 变化")
                field(entity, "trace_" + str(point["pointId"]), point.get("level"), 30)
        lc = avatar.get("equipment")
        if lc is None:
            missing.append(entity + ".equipment")
        elif not isinstance(lc, dict) or type(lc.get("tid")) is not int:
            raise CompanionError(ErrorCode.VERSION_INCOMPATIBLE, "光锥字段变化")
        else:
            eid = f"showcase-lightcone:{cid}:{lc['tid']}"
            instance = "lc_" + hashlib.sha256(canonical([account_id, form_id, lc])).hexdigest()[:32]
            equipment.append({"instance_id": instance, "entity_id": str(lc["tid"]), "owner_form_id": form_id})
            for key, maximum in (("level", 80), ("promotion", 6), ("rank", 5)):
                field(eid, key, lc.get(key), maximum)
        relics = avatar.get("relicList")
        if relics is None:
            missing.append(entity + ".relicList")
        elif not isinstance(relics, list) or len(relics) > 6:
            raise CompanionError(ErrorCode.VERSION_INCOMPATIBLE, "遗器字段变化")
        else:
            for slot, relic in enumerate(relics):
                if not isinstance(relic, dict) or type(relic.get("tid")) is not int:
                    raise CompanionError(ErrorCode.VERSION_INCOMPATIBLE, "遗器 ID 变化")
                instance = "relic_" + hashlib.sha256(canonical([account_id, form_id, slot, relic])).hexdigest()[:32]
                equipment.append({"instance_id": instance, "entity_id": str(relic["tid"]), "owner_form_id": form_id})
                field("showcase-relic:" + instance, "level", relic.get("level"), 15)
    keys = [(f["entity_id"], f["field_id"]) for f in fields]
    if len(keys) != len(set(keys)):
        raise CompanionError(ErrorCode.VERSION_INCOMPATIBLE, "公开展示包含重复字段")
    return {"account_id": account_id, "snapshot_id": query_id, "observed_at": observed_at,
            "versions": {"game": None, "region": region}, "roster_completeness": "partial",
            "characters": characters, "equipment": equipment, "fields": fields}, ttl, missing
