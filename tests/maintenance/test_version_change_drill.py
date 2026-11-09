"""Synthetic maintenance drill using real signatures, SQLite and embedded runtimes."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import uuid

import pytest

from companion.accounts import AccountService
from companion.accounts.providers.enka import EnkaProvider
from companion.accounts.refresh import AccountRefresh
from companion.contracts import CompanionError, ErrorCode, canonical
from companion.experiments.replay import save
from companion.install import Installer
from companion.knowledge.package import build_package
from companion.memory.append import MemoryAppend
from companion.memory.conflicts import Conflicts
from companion.policy import ConsentPolicy
from companion.policy.consent import binding
from companion.release.artifacts import make_artifact, open_artifact, write_release
from companion.release.signing import load_trust, test_key as new_test_key
from companion.sources.evidence import EvidenceService
from companion.sources.http import Response
from companion.storage import Store
from companion.updates.knowledge import KnowledgeSync
from companion.updates.program import ProgramUpdates
from companion.updates.source import ReleaseSource
from tests.simulation.representative_cases import case

ROOT = Path(__file__).resolve().parents[2]


def test_version_change_drill():
    base = ROOT/".local/probes/p6-maintenance"/uuid.uuid4().hex[:10]
    base.mkdir(parents=True)
    media = ROOT/"install/windows-x64"
    info = json.loads((media/"checksums.json").read_bytes())
    _, original_files, _ = open_artifact((media/info["program_artifact"]).read_bytes(), load_trust(media/"trust.json"))
    private, public = new_test_key()
    data, program = base/"data", base/"app"
    manager = Installer(program, data, trusted_keys=[public], allow_test=True)
    initial = make_artifact(original_files, kind="program", version="0.1.3", private=private,
                            inputs={"maintenance_scope":"synthetic next-version drill; not a game rule"})
    assert manager.install(initial)["version"] == "0.1.3"
    store = Store(data/"personal")
    AccountService(store).configure("maint-a", style="A", region="ASIA", uid="100000001")
    account_before = store.require_account("maint-a")
    memory = MemoryAppend(store)
    old = memory.append("maint-a","conclusion","合成维护旧结论","旧合成假设每回合一个计数，仅用于维护验收。","合成规则1",
        topic="maintenance",conditions=["合成规则1，不代表游戏"],game_version="4.6",claim_key="maintenance-counter",source_refs=["knowledge:test-turn@0.5.0"])
    old_id = old.data["research_id"]
    old_body = store.read_research("maint-a",old_id)
    saved = save(store,"maint-a",case())
    experiment_id = saved.data["experiment_id"]
    assert saved.data["comparison"]["outcomes"][0]["expected_damage"] == 9720
    before_payload = None
    with store.connection() as connection:
        before_payload = connection.execute("SELECT payload FROM experiments WHERE id=?",(experiment_id,)).fetchone()[0]

    knowledge_input = base/"knowledge-input"
    shutil.copytree(ROOT/"tests/fixtures/knowledge/source",knowledge_input)
    knowledge_source_dir = base/"knowledge-source"
    original_body = (knowledge_input/"combat/test-turn.md").read_text(encoding="utf-8")
    def publish_knowledge(version):
        package = build_package(knowledge_input,version=version)
        content = make_artifact({"package.json":package.encode()},kind="knowledge",version=version,private=private)
        write_release(knowledge_source_dir,content,"knowledge.TEST.json",private)
    publish_knowledge("0.5.0")
    clock = [0]
    sync = KnowledgeSync(data/"knowledge",source=ReleaseSource(knowledge_source_dir,trusted_keys=[public],require_signature=True,allow_test=True),clock=lambda:clock[0],interval=60)
    assert sync.sync().data["version"] == "0.5.0"
    (knowledge_input/"combat/test-turn.md").write_text(original_body+"\n合成维护新假设：计数改为两个；不是游戏事实。\n",encoding="utf-8")
    publish_knowledge("0.5.1"); clock[0]=61
    assert sync.sync().data["version"] == "0.5.1"
    assert manager.state()["current"]["version"] == "0.1.3"
    evidence = EvidenceService(store).register("maint-a","maintenance-counter","https://example.com/synthetic-maintenance",
        sync.current().bodies["combat/test-turn.md"],kind="manual",applicable_version="synthetic-maintenance",stance="opposes",source_ref="synthetic-local-signed-knowledge:0.5.1")
    conflict = Conflicts(store).propose("maint-a",old_id,[evidence.data["registered_id"]],"新旧合成假设适用条件不同；等待玩家选择",
        "旧计数1仅适用于0.5.0合成规则，新假设2需重新讨论。","限制旧结论到原合成版本",action="restrict",conditions=["只限知识0.5.0合成规则1"])
    assert conflict.data["old_body_unchanged"] and store.read_research("maint-a",old_id)==old_body

    files = dict(original_files)
    prefix = "runtime/Lib/site-packages/companion/"
    files[prefix+"__init__.py"] = files[prefix+"__init__.py"].replace(b'"0.1.3"',b'"0.1.4"')
    files[prefix+"experiments/contracts.py"] = files[prefix+"experiments/contracts.py"].replace(b'RULES_VERSION = "p3-1"',b'RULES_VERSION = "maintenance-p3-2"')
    rule_path = prefix+"resources/manifests/analysis-mechanics.json"
    rules = json.loads(files[rule_path]); rules["data_version"]="synthetic-maintenance-kit-v2"
    rules["scope"]="Synthetic maintenance only; not game facts"
    rules["characters"]["1002:base"]["actions"]["skill"]["multiplier"]=3.6
    rules["characters"]["1002:base"]["source_ref"]="synthetic:maintenance-rule-v2"
    rules["characters"]["1002:base"]["source_sha256"]=hashlib.sha256(b"synthetic skill 3.6, not game data").hexdigest()
    files[rule_path]=canonical(rules)
    for short in ("moc","pf","as","aa"):
        key=prefix+f"resources/examples/{short}-comparison.json"
        example=json.loads(files[key]);example["request"]["data_version"]=rules["data_version"];files[key]=canonical(example)
    next_program = make_artifact(files,kind="program",version="0.1.4",private=private,inputs={"maintenance_scope":"synthetic rule and interface version change"})
    program_source_dir=base/"program-source"
    write_release(program_source_dir,next_program,"program.TEST.json",private)
    updates = ProgramUpdates(store,program,source=ReleaseSource(program_source_dir,trusted_keys=[public],require_signature=True,allow_test=True),current_version="0.1.3")
    plan=updates.check(force=True).data["plan"]
    assert plan and manager.state()["current"]["version"]=="0.1.3"
    with store.connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM confirmations").fetchone()[0]==0

    api_calls=[]
    def changed_api(url):
        api_calls.append(url)
        return Response(200,b'{"new_api_shape":true}',{})
    with pytest.raises(CompanionError) as error:
        AccountRefresh(store,provider=EnkaProvider(transport=changed_api)).refresh("maint-a","user:synthetic-interface-change","refresh")
    assert error.value.code==ErrorCode.VERSION_INCOMPATIBLE and len(api_calls)==1
    assert store.require_account("maint-a")==account_before and store.latest_snapshot("maint-a") is None

    receipt={"source_kind":"host_native","source_ref":"synthetic-maintenance-adapter-only","host_permission":"approved","decision":"approve","binding_sha256":binding(plan)}
    reference=ConsentPolicy(store).record_verified(plan["id"],receipt,verifier=lambda supplied,expected: supplied is receipt and expected==binding(plan))
    assert updates.apply(plan["id"],reference,offline=True).data["version"]=="0.1.4"
    env=os.environ.copy();env.pop("PYTHONPATH",None);env.update(PYTHONUTF8="1",PYTHONIOENCODING="utf-8",HSR_COMPANION_INSTALL_ROOT=str(program))
    runtime_records=[]
    def call(operation,arguments):
        python=program/"versions"/manager.state()["current"]["digest"]/"runtime/python.exe"
        process=subprocess.run([str(python),"-I","-m","companion","--data-dir",str(data),"--offline","call",operation,"--input","-"],
            input=canonical(arguments),capture_output=True,env=env,timeout=40)
        value=json.loads(process.stdout);runtime_records.append({"operation":operation,"exit_code":process.returncode,"result":value})
        assert process.returncode==0,value
        return value
    assert call("calculation_schema",{"kind":"damage"})["versions"]["rules"]=="maintenance-p3-2"
    new_request=deepcopy(case());new_request["data_version"]=rules["data_version"];new_request["assumptions"].append("仅维护合成倍率3.6，不是游戏事实")
    fresh=call("simulation_compare",{"request":new_request})
    assert fresh["data"]["outcomes"][0]["expected_damage"]==12420
    replayed=call("experiment_replay",{"account_id":"maint-a","experiment_id":experiment_id})
    assert replayed["data"]["same_result"] and replayed["data"]["archived_program"]["version"]=="0.1.3"
    assert replayed["data"]["comparison"]["outcomes"][0]["expected_damage"]==9720
    assert store.read_research("maint-a",old_id)==old_body
    later=memory.append("maint-a","discussion","升级后新研究","回滚后这条新研究也要保留。","新研究保留",topic="maintenance")

    damaged=sync.current();sync.files.path(f"packages/{damaged.fingerprint}/package.json").write_bytes(b"corrupt synthetic package")
    assert sync.recover()["version"]=="0.5.0"
    (knowledge_input/"combat/test-turn.md").write_text(original_body,encoding="utf-8")
    publish_knowledge("0.5.2");clock[0]=122
    assert sync.sync().data["version"]=="0.5.2"
    assert sync.current().bodies["combat/test-turn.md"]==original_body
    assert manager.rollback()["version"]=="0.1.3"
    assert store.read_research("maint-a",later.data["research_id"])=="回滚后这条新研究也要保留。"
    assert store.read_research("maint-a",old_id)==old_body
    with store.connection() as connection:
        assert connection.execute("SELECT state FROM revision_plans WHERE id=?",(conflict.data["plan_id"],)).fetchone()[0]=="proposed"
        assert connection.execute("SELECT payload FROM experiments WHERE id=?",(experiment_id,)).fetchone()[0]==before_payload
        assert connection.execute("SELECT consumed_at FROM confirmations WHERE id=?",(reference,)).fetchone()[0]
    report={"status":"PASS","source_program_sha256":info["program_sha256"],"test_root":str(base),
        "knowledge_versions":["0.5.0","0.5.1","0.5.2"],"program_versions":["0.1.3","0.1.4","0.1.3"],
        "automatic_knowledge_sync_with_controlled_clock":True,"old_research_unchanged":True,"conflict_still_pending":True,
        "program_only_notified_before_confirmation":True,"bound_confirmation_consumed":True,
        "synthetic_new_rule_result":12420,"original_snapshot_result":9720,"old_experiment_payload_unchanged":True,
        "interface_change_preserved_account":True,"fake_interface_calls":len(api_calls),"actual_uid_http_requests":0,
        "bad_knowledge_recovered_and_corrected_by_higher_version":True,"new_research_survived_rollback":True,
        "layer":"real embedded runtimes, signed TEST releases, SQLite; synthetic receipt adapter and controlled TTL clock; not real model or game calibration",
        "runtime_records":runtime_records}
    evidence=ROOT/".local/evidence/D058";evidence.mkdir(parents=True,exist_ok=True)
    (evidence/"drill.json").write_bytes(canonical(report))
