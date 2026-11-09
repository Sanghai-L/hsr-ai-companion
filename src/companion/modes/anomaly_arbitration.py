"""Roster pressure and a conditional Knight projection, separate from King clears."""
from .analysis import finish

RULES = {"id": "aa-released-rules-20261108", "kind": "historical_rule_summary", "observed_at": "2026-11-08",
         "knight_slots": 3, "king_slots": 1, "characters_unique_between_knights": True,
         "equipment_unique_between_knights": True, "king_can_reuse_knight_resources": True,
         "period": "generic-no-current-claim",
         "source_refs": ["https://wiki.biligame.com/sr/异相仲裁", "https://honkai-star-rail.fandom.com/wiki/Anomaly_Arbitration"],
         "source_scope": "公开规则正文摘要；未核对当前期数敌人／裁决象限，不自动推断当期条件"}


def analyze(request=None):
    guidance = ["分别登记三个骑士的队伍、光锥和遗器实例；角色不同形态仍占用同一角色资源",
                "优先保留各骑士必需的辅助和生存位；王棋可复用骑士资源，不能把骑士互斥限制延伸到王棋",
                "逐项检查敌人特性与裁决象限；未知特性只作定性讨论。单个骑士的输出比较不代表王棋、星数或整期通关"]
    return finish("anomaly_arbitration", request, guidance,
                  quantitative_scope="单个代表性骑士配置的直伤比较；三队合法性及王棋复用由multi_team_plan检查",
                  extra={"roster_rules": RULES, "quantitative": "指定固定窗口普通直伤与资源", "qualitative": "敌人特性适配、生存、王棋策略和未量化辅助价值"})
