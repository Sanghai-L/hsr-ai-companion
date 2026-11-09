"""Close D057 only against the measured signed candidate and actual installation evidence."""
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from companion import __version__
from companion.release.artifacts import open_artifact
from companion.release.signing import load_trust
from tools.p6.record import record, write

ROOT = Path(__file__).resolve().parents[2]


def main():
    ledger = json.loads((ROOT/"docs/development/task-status.json").read_bytes())
    assert all(t["status"] == "DONE" for t in ledger["tasks"] if int(t["id"][1:]) <= 56)
    cases = ET.parse(ROOT/".local/evidence/P6/all-before-install.xml").getroot().findall(".//testcase")
    assert len(cases)==356 and all(c.find("failure") is None and c.find("error") is None and c.find("skipped") is None for c in cases)
    media = ROOT/"install/windows-x64"
    checksums = json.loads((media/"checksums.json").read_bytes())
    content = (media/checksums["program_artifact"]).read_bytes()
    rebuilt = (ROOT/".local/dist/p6-rc-rebuild/program"/checksums["program_artifact"]).read_bytes()
    assert content == rebuilt and hashlib.sha256(content).hexdigest() == checksums["program_sha256"]
    metadata, payload, identity = open_artifact(content, load_trust(media/"trust.json"))
    assert metadata["version"]==__version__=="0.1.3" and identity["channel"]=="production"
    for path in (ROOT/"src/companion").rglob("*.py"):
        key = "runtime/Lib/site-packages/companion/"+path.relative_to(ROOT/"src/companion").as_posix()
        assert payload[key] == path.read_bytes(), key
    assert all(not any(p in {".local", ".venv", "tests"} for p in Path(name).parts) and not name.endswith((".dpapi", ".sqlite3", ".pem")) for name in payload)
    host = json.loads((ROOT/".local/evidence/D054/final.json").read_bytes())
    install = json.loads((ROOT/".local/evidence/D056/repository-8ba0d76245/result.json").read_bytes())
    assert host["final_pass"]==50 and host["critical_failures"]==0 and install["status"]=="PASS"
    gate = {"status":"PASS_DECLARED_WINDOWS_CODEX_SCOPE", "task":"D057", "version":__version__,
            "program_sha256":checksums["program_sha256"], "business_sha256":metadata["inputs"]["business_sha256"],
            "identity":identity,"reproducible_bytes":True,"app_source_matches_signed_package":True,
            "tested_repository_commit":install["commit"],"regression":{"passed":356,"failed":0,"skipped":0,"live_deselected":1},
            "host_distinct_cases":50,"actual_model_sessions_to_date":12,"core_blockers":[],
            "declared_support":"Win11 build26200 x64, Codex0.167.0-alpha.3.2 / gpt-6.1-sol max; independent environment, not VM",
            "license":"all rights reserved for original material; retained third-party notices", "formal_github_release_created":False,
            "remaining_stage_task":"D058 synthetic maintenance drill, not a D057 prerequisite"}
    write(".local/evidence/D057/gate.json",gate)
    write("docs/gates/P6-release-candidate.json",gate)
    text = f'''# P6 发布候选关口

2026-11-09：D057通过，状态 **PASS_DECLARED_WINDOWS_CODEX_SCOPE**。候选版本0.1.3，属于已声明Windows／Codex范围；尚未创建正式GitHub Release，不改称完整v1.0已公开发布。

- 程序SHA-256：{gate['program_sha256']}。
- 同一源码、依赖和身份两次构建逐字节一致；当前全部应用Python源码与已签名包一致。
- 356项全量离线回归通过，0失败／0跳过，1项UID live明确未选择。50个中文真实宿主用例首次48/50，修复帮助发现后两题复测通过，关键错误0；另有1个真实仓库安装会话。
- 仓库固定提交41f17a0的真实安装、原生MCP、独立CLI重启重算、合成升级回滚、卸载保留用户内容、公开签名源均有证据。细节及独立环境／非VM限制见[Windows矩阵](../validation/windows-install-matrix.md)。
- 原创部分保留所有权利，第三方许可与运行文件保留；对外树按白名单排除私有资料与私钥。真实账号／UID未参与本轮。

当前只承诺已测Win11／Codex组合，另两宿主暂缓。只量化清单内动作、E0无大行迹的假设窗口，当前期数证据不足时降级；完整敌人AI、全角色、精确实战得分与通关概率未宣称支持。短计算按预算同步返回，不提供后台任务断点续算。

需求A01～A24已按当前范围复核，详见本机需求追踪；公开覆盖见[coverage](../coverage.md)。关键证据：.local/evidence/D057/gate.json、P6/all-before-install.xml、D054/final.json、D056/。原始轨迹与个人目录仅留本机。

下一项D058：合成知识／规则／接口变更、批准更新、旧快照重算与撤回恢复演练；完成记录将附在维护就绪关口。
'''
    (ROOT/"docs/gates/P6-release-candidate.md").write_text(text,encoding="utf-8")
    record("D057",status="DONE",artifacts=["docs/gates/P6-release-candidate.md","docs/gates/P6-release-candidate.json","docs/release/release-notes.md","install/windows-x64","install/knowledge"],
           commands=["python tools/build_release.py --key <本机DPAPI身份> --update-base <已批准仓库源> --output <重复构建目录>","python -m tools.p6.freeze_candidate"],
           evidence=[".local/evidence/D057/gate.json",".local/evidence/P6/all-before-install.xml",".local/evidence/D054/final.json",".local/evidence/D056/published-snapshot.json"],
           summary="当前Win11/Codex候选关口通过；356回归、50题与仓库安装证据绑定同一f921428d程序包，重复构建逐字节一致；未建正式Release",
           counts={"passed":356,"failed":0,"skipped":0})
    print(json.dumps({"D057":"DONE","version":__version__,"program_sha256":gate["program_sha256"]}))


if __name__=="__main__":
    main()
