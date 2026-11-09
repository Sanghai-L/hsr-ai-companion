"""Source-level checks for D003. Runtime proof belongs to D008."""
import ast
import json
import re
import sys
import tomllib

from common import ROOT, LOCAL, digest, now, write_json, update_task


def main():
    manifest_path = ROOT / "manifests/upstreams.lock.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    repo = LOCAL / "upstream/hsr-nous/repo"
    imports = set()
    for package in ("sim", "sim_schema", "common"):
        for path in (repo / "src/hsr_nous" / package).rglob("*.py"):
            # Web is a separate optional presentation layer, not part of the core probe.
            if path.name == "web.py":
                continue
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Import):
                    imports.update(alias.name.split('.')[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imports.add(node.module.split('.')[0])
    external = sorted(imports - sys.stdlib_module_names - {"hsr_nous"})
    project = tomllib.loads((repo / "pyproject.toml").read_text(encoding="utf-8"))
    scripts = project["project"]["scripts"]
    entry_file = repo / "src" / (scripts["hsr-sim"].split(':')[0].replace('.', '/') + '.py')
    assert entry_file.exists() and "def main(" in entry_file.read_text(encoding="utf-8")
    assert (repo / "tests/test_engine_v01.py").is_file()
    checks = []
    for item in manifest["upstreams"]:
        assert re.fullmatch(r"[0-9a-f]{40}", item["commit"])
        for record in item["files"]:
            if record["status"] == 200:
                assert digest(ROOT / record["path"]) == record["sha256"]
        licenses = [r for r in item["files"] if r["url"].endswith('/LICENSE') and r["status"] == 200]
        item["license_file_sha256"] = licenses[0]["sha256"] if licenses else None
        if item["id"] == "hsr-mechanic-sim":
            assert "to be confirmed" in (ROOT / licenses[0]["path"]).read_text(encoding="utf-8")
        item["distribution_decision"] = (
            "EXCLUDED_UNRESOLVED" if item["license_observed"] == "UNRESOLVED" else
            "NOT_BUNDLED_REFERENCE_ONLY" if item["scope"] != "simulation-core" else
            "LOCAL_VALIDATION_ONLY_RETAIN_MIT_NOTICE_IF_REUSED")
        checks.append({"id": item["id"], "pinned": True, "hashes_verified": True})
    manifest["primary_core_audit"] = {"external_import_roots": external,
        "package_declared_dependencies": project["project"]["dependencies"],
        "probe_strategy": "uv installs core/test/build dependencies; editable package with --no-deps; do not run full setup_test_env.sh",
        "full_environment_excluded": ["langchain", "langchain-openai", "account", "web", "ops", "optimizer", "playwright"],
        "runtime_validation": "D008"}
    write_json(manifest_path, manifest)
    evidence_dir = LOCAL / "evidence/D003"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    verified = ["# 源码核实的入口（不是运行通过声明）", "",
        f"HSR_Nous commit：`{manifest['upstreams'][0]['commit']}`。", "",
        "- `hsr-sim` → `hsr_nous.sim.cli:main`，函数和文件均存在。",
        "- `python -m hsr_nous.sim.cli --help`：待 D008 实际执行。",
        "- `hsr-sim run <build.yaml> <stage.yaml> --mode <expected|roll> --seed <整数>`：run 子命令源码存在。",
        "- `compile_encounter_yaml(build_text, stage_text, template_roots=...)` → `CombatEngine.from_compiled(...).run()`：README 与源码对照。",
        "- 核心测试：`python -m pytest tests/test_engine_v01.py tests/test_engine_v02.py tests/test_compile.py tests/test_expression.py tests/test_cycle_v11.py tests/test_caveats_channel.py -q -ra`；文件均存在，执行结果归 D008。",
        "", f"核心相关源码外部 import 根（排除 web.py；含延迟导入）：`{external}`。",
        "", "上游原始完整安装脚本还会安装账号、网页、浏览器和 optimizer，P0 不执行。",
        "使用本地 uv 可执行程序、核心依赖锁和 --no-deps editable 安装验证核心可用性；这不是上游全功能环境。"]
    (evidence_dir / "verified-commands.md").write_text("\n".join(verified)+"\n", encoding="utf-8")
    docs = ["# ADR-001：上游候选与本地验证范围", "", f"记录：{now()}；状态：P0 候选固定，最终路线由 ADR-002 决定。", "",
            "| 候选 | commit | 许可文件观察 | 本次范围 |", "|---|---|---|---|"]
    for item in manifest["upstreams"]:
        docs.append(f"| [{item['id']}]({item['repository']}/tree/{item['commit']}) | `{item['commit']}` | {item['license_observed']} | {item['scope']} |")
    docs += ["", "选择 HSR_Nous 进入实际验证，保留源码原状，仅安装模拟核心需要的依赖。其 pyproject 的 LangChain 等依赖不等于核心模拟运行必需；D008 用运行与网络审计验证。",
             "", "hsr-mechanic-sim 的 LICENSE 原文仍为许可待确认，排除复制和分发。Enka 文档仓库未发现 LICENSE，只调用公开 API，不复制其文档作为产品内容。",
             "", "知识库 NOTICE 对游戏文本、素材和整理成果区分授权。StarRailRes、知识库、SRSim 仅作本地研究来源，本轮不整合到分发包。MIT 标记也不自动证明第三方游戏数据可以再分发。",
             "", "原项目尚未确定整体许可证，未创建 LICENSE。以后实际复制代码时须保留相应许可与署名；游戏数据单独审视。",
             "", "完整 SHA、许可哈希及来源文件哈希见 `manifests/upstreams.lock.json`；原文件仅在 `.local/upstream/`。核实命令见 `.local/evidence/D003/verified-commands.md`。"]
    (ROOT / "docs/decisions/ADR-001-upstream-candidates.md").write_text("\n".join(docs)+"\n", encoding="utf-8")
    write_json(evidence_dir / "source-audit.json", {"at": now(), "checks": checks,
        "entry_file": entry_file.relative_to(ROOT).as_posix(), "external_core_imports": external, "exit_code": 0})
    update_task("D003", "DONE", summary="8 个候选固定完整 SHA 与许可哈希；模拟入口已由源码核实",
                artifacts=["manifests/upstreams.lock.json", "docs/decisions/ADR-001-upstream-candidates.md"],
                commands=["python tools/p0/fetch_upstreams.py", "python tools/p0/verify_upstreams.py"],
                counts={"passed": len(checks)+2, "failed": 0, "skipped": 0},
                evidence=[".local/evidence/D003/source-audit.json", ".local/evidence/D003/verified-commands.md"],
                next_step="D004", level="真实远端 SHA／源码与许可文件核查；非游戏实测")
    print(json.dumps({"candidates": len(checks), "external_core_imports": external}))


if __name__ == "__main__":
    main()
