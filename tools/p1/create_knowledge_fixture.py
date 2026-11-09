"""Three original synthetic entries; no upstream text or current game claims."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "tests/fixtures/knowledge/source"


def main():
    for category, key, title, body in [
        ("combat", "test-turn", "合成行动样例", "这是基础工程测试知识。假设测试角色每回合获得一个计数；它不是游戏机制结论。"),
        ("characters", "test-form", "合成形态样例", "这是原创测试条目。测试角色的甲、乙形态使用不同 ID，示例不对应真实角色。"),
        ("basics", "test-unknown", "未知资料说明", "未知值与已知的零不同；未展示的测试装备不能被推断为未持有。")]:
        directory = ROOT / category
        directory.mkdir(parents=True, exist_ok=True)
        (directory / f"{key}.md").write_text(body + "\n", encoding="utf-8")
        value = {"id": key, "category": category, "title": title, "aliases": [],
                 "version_min": "synthetic", "version_max": "synthetic", "information_state": "unknown",
                 "evidence": "hypothesis", "body_path": f"{category}/{key}.md", "conditions": ["仅用于工程验证"],
                 "exceptions": [], "sources": [{"type": "synthetic", "ref": "project-original-fixture",
                    "observed_at": "2026-11-06T00:00:00Z", "license": "original-test-fixture"}],
                 "verified_at": "2026-11-06T00:00:00Z", "license": "original-test-fixture"}
        (directory / f"{key}.json").write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

