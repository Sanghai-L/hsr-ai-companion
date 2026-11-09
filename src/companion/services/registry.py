"""One operation registry shared by CLI and MCP; unavailable means unavailable."""
import base64
from dataclasses import dataclass
import hashlib
import json
import platform
import sys

from jsonschema import Draft202012Validator

from companion import __version__
from companion.contracts import CompanionError, ErrorCode, ToolResult, canonical

MAX_RESULT_BYTES = 65536


def input_schema(properties=None, required=()):
    return {"type": "object", "properties": properties or {}, "required": list(required), "additionalProperties": False}


@dataclass
class Operation:
    name: str
    description: str
    schema: dict
    handler: object
    read_only: bool = False

    def tool(self):
        return {"name": self.name, "description": self.description, "inputSchema": self.schema,
                "annotations": {"readOnlyHint": self.read_only, "destructiveHint": False,
                                "openWorldHint": self.name in {"session_bootstrap", "updates_check", "knowledge_sync", "program_update_propose", "source_fetch", "account_refresh", "current_stage_check"}}}


class Registry:
    def __init__(self, context):
        self.context = context
        self.operations = {}
        self.unavailable = {
            "source_fetch": "D023", "evidence_register": "D023",
            "account_refresh": "D024", "account_patch": "D024", "memory_append": "D025",
            "memory_search": "D025", "research_replace": "D026", "calculate": "D030～D032",
            "plan_pulls": "D033", "simulation_preflight": "D036", "simulation_submit": "D039",
            "simulation_status": "D039", "simulation_result": "D039", "simulation_cancel": "D039",
            "simulation_compare": "D040", "experiment_replay": "D041", "program_update_apply": "D051"}
        self.add("doctor", "只读检查本地运行环境；不安装依赖、不查 UID。", input_schema(), self.doctor, True)
        self.add("status", "读取脱敏初始化状态；不刷新账号。", input_schema(), self.status, True)
        page = {"cursor": {"type": ["string", "null"], "maxLength": 512}, "page_size": {"type": "integer", "minimum": 1, "maximum": 20}}
        self.add("capabilities", "分页列出当前已实现和未实现的能力。", input_schema(page), self.capabilities, True)
        from companion.install.help import local_help
        self.add("local_help", "只读查询已实现的安装、更新确认、恢复、卸载及去敏诊断命令；不知道命令名时先查，不执行操作。",
                 input_schema({"topic": {"enum": ["all", "diagnostics", "install", "updates"]}}), local_help, True)
        self.add("updates_check", "检查维护者知识／程序发布；知识自动同步，程序只提示。",
                 input_schema({"kind": {"enum": ["all", "knowledge", "program"]}, "force": {"type": "boolean"}}), self.updates_check)
        self.add("knowledge_sync", "从已配置维护者源自动同步兼容的内容包，不更新代码或账号。",
                 input_schema({"force": {"type": "boolean"}}), lambda force=False: context.knowledge().sync(force=force, offline=context.offline))
        self.add("program_update_propose", "读取维护者程序发布并保存版本／指纹绑定方案；不安装。",
                 input_schema({"target_version": {"type": "string", "pattern": r"^\d+\.\d+\.\d+$"}}),
                 lambda target_version=None: context.program().check(force=True, offline=context.offline, target_version=target_version))
        self.add("program_update_apply", "安装已校验签名且有对应一次性用户确认的程序方案。",
                 input_schema({"plan_id": {"type": "string", "maxLength": 80}, "confirmation_id": {"type": "string", "maxLength": 80}}, ("plan_id", "confirmation_id")),
                 lambda plan_id, confirmation_id: context.program().apply(plan_id, confirmation_id, offline=context.offline))
        self.unavailable.pop("program_update_apply", None)
        self._add_session()
        self._add_knowledge()
        self._add_sources()
        self._add_accounts_p2()
        self._add_memory()
        self._add_revisions()
        self._add_quantitative()
        self._add_simulation()
        self._add_representative_analysis()

    def _add_representative_analysis(self):
        from companion.resources import resource_text
        from companion.simulation.compare import compare
        from companion.modes.analysis import MODES, analyze, schema, select_mode
        from companion.planning.multi_team import plan
        from companion.planning.sensitivity import analyze as sensitivity
        from companion.sources.current_stages import check_current
        from companion.experiments.replay import save, replay
        request_schema = json.loads(resource_text("schemas", "representative-comparison.schema.json"))
        mode = {"enum": list(MODES)}
        account = {"type": "string", "minLength": 1, "maxLength": 80}
        self.unavailable.pop("simulation_compare", None)
        self.unavailable.pop("experiment_replay", None)
        self.add("mode_select", "从玩法名称选择四模式分析模板；多模式或不明确时返回缺项。",
                 input_schema({"query": {"type": "string", "minLength": 1, "maxLength": 1000}}, ["query"]), select_mode, True)
        self.add("analysis_schema", "读取简化比较的完整合同、对应模式示例及限定技能覆盖；示例是明确假设，不代表玩家练度。",
                 input_schema({"mode": mode}), schema, True)
        self.add("simulation_compare", "同场景、时间窗和资源策略下比较2～4个队伍／配置；仅简化输出，缺关键机制或中止时不排名。",
                 input_schema({"request": request_schema}, ["request"]), compare, True)
        self.add("mode_analyze", "四模式指导与代表性比较；无request时给定性方向，资料不足不编分数、通关概率或当前效果。",
                 input_schema({"mode": mode, "request": request_schema}, ["mode"]), analyze, True)
        self.add("comparison_save", "重新计算并保存指定账号私有实验的输入、规则指纹、结果和假设；不改账号事实或研究结论。",
                 input_schema({"account_id": account, "request": request_schema}, ["account_id", "request"]),
                 lambda account_id, request: save(self.context.store, account_id, request))
        self.add("experiment_replay", "按experiment_id从保存输入重新计算；检验结果一致性，非断点续算；不刷新UID。",
                 input_schema({"account_id": account, "experiment_id": account}, ["account_id", "experiment_id"]),
                 lambda account_id, experiment_id: replay(self.context.read_store, account_id, experiment_id), True)
        self.add("multi_team_plan", "在明确假设可用清单中分配少量候选；检查角色／形态与装备实例冲突，异相王棋可复用骑士资源；只推荐给定候选集。",
                 input_schema({"request": json.loads(resource_text("schemas", "multi-team.schema.json"))}, ["request"]), plan, True)
        self.add("sensitivity_analyze", "对1～2个关键参数逐项使用2～3种条件重算，返回推荐反转条件；无随机置信区间。",
                 json.loads(resource_text("schemas", "sensitivity.schema.json")), sensitivity, True)
        self.add("current_stage_check", "核对正式服资料源和期数并冻结来源哈希；排期／区服未知则降级为历史通用条件；不读UID。",
                 input_schema({"mode": mode, "period_id": {"type": "string", "pattern": r"^\d{1,8}$"},
                               "region": {"enum": ["ASIA", "EU", "NA", "CN", "TW_HK_MO"]}}, ["mode"]),
                 lambda mode, **kwargs: check_current(self.context.sources(), mode, offline=self.context.offline, **kwargs))

    def _add_simulation(self):
        from copy import deepcopy
        from companion.resources import resource_text
        from companion.simulation.preflight import preflight
        from companion.simulation.builds import validate_build
        schema = json.loads(resource_text("schemas", "experiment.schema.json"))
        schema.pop("$schema", None)
        schema["properties"]["kind"] = {"const": "simulation"}
        schema["properties"]["parameters"] = json.loads(resource_text("schemas", "simulation-parameters.schema.json"))
        self.unavailable.pop("simulation_preflight", None)
        self.add("simulation_schema", "读取战斗模拟的完整数据合同、工程示例及当前可用范围；没有执行模拟，不刷新UID。",
                 input_schema(), lambda: ToolResult(data={"experiment_schema": deepcopy(schema),
                     "example_request": json.loads(resource_text("examples", "simulation.json")),
                     "available": ["simulation_preflight", "simulation_build_validate", "simulation_build_import"],
                     "simplified_contract_operation": "analysis_schema",
                     "simplified_available": ["simulation_compare", "mode_analyze", "comparison_save", "experiment_replay"],
                     "limitations": "首个历史混沌场景的完整敌人机制尚未验收；工程诊断不能预测通关或生成游戏收益排名"}), True)
        self.add("simulation_preflight", "从实际构筑和冻结场景检查全部必要机制；未知／缺失阻断高精度，返回具体影响，不执行战斗、不刷新UID。",
                 input_schema({"experiment": schema}, ["experiment"]), preflight, True)
        self.add("simulation_build_validate", "验证独立构筑的角色／装备占用、等级／行迹绑定、面板来源和速度精度；不会保存或修改账号。",
                 input_schema({"build": json.loads(resource_text("schemas", "simulation-build.schema.json"))}, ["build"]),
                 lambda build: self._build_validation_result(validate_build(build)), True)
        self.add("simulation_build_import", "读取指定账号的本地快照生成独立构筑；只补玩家明确给出的字段，缺装备不猜毕业练度，假设不写回账号；不刷新UID。",
                 input_schema({"account_id": {"type": "string", "maxLength": 80},
                               "form_ids": {"type": "array", "minItems": 4, "maxItems": 4, "uniqueItems": True,
                                            "items": {"type": "string", "maxLength": 100}},
                               "overrides": {"type": "object", "maxProperties": 4}, "hypothesis": {"type": "boolean"},
                               "assumptions": {"type": "array", "maxItems": 30, "items": {"type": "string", "minLength": 1, "maxLength": 1500}}}, ["account_id", "form_ids"]),
                 lambda account_id, form_ids, **kwargs: self._import_simulation_build(account_id, form_ids, **kwargs), True)

    def _import_simulation_build(self, account_id, form_ids, **kwargs):
        from companion.simulation.builds import import_result
        snapshot = self.context.read_store.latest_snapshot(account_id)
        if snapshot is None:
            raise CompanionError(ErrorCode.MISSING_DATA, "该账号尚无本地资料快照", details={"fields": ["account_snapshot"]})
        return import_result(snapshot, form_ids, **kwargs)

    @staticmethod
    def _build_validation_result(report):
        return ToolResult(status="partial" if not report["executable"] or report["limitations"] else "success",
                          data=report, warnings=report["limitations"], missing_fields=report["missing_fields"])

    def _add_quantitative(self):
        from copy import deepcopy
        from companion.resources import resource_text
        from companion.experiments.service import execute
        from companion.experiments.contracts import compare_request
        base = json.loads(resource_text("schemas", "experiment.schema.json"))
        variants = []
        for kind, schema_name in (("damage", "damage-parameters"), ("timeline", "timeline-parameters"),
                                   ("gacha", "gacha-parameters"), ("pull_plan", "pull-plan-parameters")):
            variant = deepcopy(base)
            variant.pop("$schema", None)
            variant["properties"]["kind"] = {"const": kind}
            variant["properties"]["parameters"] = json.loads(resource_text("schemas", schema_name + ".schema.json"))
            variants.append(variant)
        self.unavailable.pop("calculate", None)
        self.unavailable.pop("plan_pulls", None)
        self.add("calculation_schema", "读取一种 P3 计算的完整实验／参数合同及原创示例。字段不明确先调用本工具，不需要搜索源码、仓库或宿主文件；示例不是玩家事实。",
                 input_schema({"kind": {"enum": ["damage", "timeline", "gacha", "pull_plan"]}}, ["kind"]),
                 lambda kind: self.calculation_schema(kind, variants), True)
        self.add("calculate", "P3 只读定量计算。experiment 带版本、条件、预算和来源；kind 为 damage（普通直伤）、timeline（局部行动与资源）、gacha（DP）。逐抽软保底非官方精确曲线；未知保底返回范围。",
                 input_schema({"experiment": {"oneOf": variants[:3]}}, ["experiment"]), execute, True)
        self.add("plan_pulls", "P3 只读抽卡规划：手工预算、三种收入、独立卡池状态和顺序目标；始终包括不抽方案，可达性与固定状态／定性收益分开；不刷新 UID。",
                 input_schema({"experiment": variants[3]}, ["experiment"]),
                 lambda experiment: execute(experiment, planning_only=True), True)
        self.add("experiment_compare", "检查比较双方版本、模式、投资口径及预算；差异需要显式说明，不同口径不生成排名。",
                 json.loads(resource_text("schemas", "comparison.schema.json")),
                 lambda **kwargs: compare_request(kwargs), True)

    def calculation_schema(self, kind, variants):
        from companion.resources import resource_text
        from companion.experiments.contracts import RULES_VERSION
        index = ["damage", "timeline", "gacha", "pull_plan"].index(kind)
        sample_name = "pull-plan" if kind == "pull_plan" else kind
        sample = json.loads(resource_text("examples", sample_name + ".json"))
        sample["experiment"]["versions"]["engine"] = __version__
        sample["experiment"]["versions"]["rules"] = RULES_VERSION
        return ToolResult(data={"kind": kind, "experiment_schema": variants[index], "example_request": sample,
                               "example_policy": "原创合成结构示例，不是玩家账号事实；实际输入须替换为玩家明确提供或有来源的条件",
                               "units": "damage: flat属性、比例加成(0.5=50%); timeline: speed/AV/energy/SP; gacha: pity=已连续未出五星的抽数; budget: jade/tickets"},
                          versions={"engine": __version__, "rules": RULES_VERSION})

    def _add_revisions(self):
        from companion.memory.conflicts import Conflicts
        from companion.memory.revisions import Revisions
        self.unavailable.pop("research_replace", None)
        text = lambda maximum: {"type": "string", "minLength": 1, "maxLength": maximum}
        account = {"account_id": text(80)}
        self.add("memory_conflict_propose", "登记新证据与旧结论的冲突及修订方案；旧文不变，等待玩家回复。",
                 input_schema({**account, "research_id": text(80), "evidence_ids": {"type": "array", "minItems": 1, "maxItems": 30, "items": text(80)},
                               "reason": text(1500), "new_body": text(24000), "new_summary": text(1500),
                               "action": {"enum": ["replace", "restrict", "retract"]},
                               "conditions": {"type": "array", "maxItems": 20, "items": text(1000)}},
                              ["account_id", "research_id", "evidence_ids", "reason", "new_body", "new_summary"]),
                 lambda **kwargs: Conflicts(self.context.store).propose(**kwargs))
        self.add("memory_revision_get", "分页查看待确认修订的完整具体内容和方案指纹。",
                 input_schema({**account, "plan_id": text(80), "offset": {"type": "integer", "minimum": 0},
                               "limit": {"type": "integer", "minimum": 1, "maximum": 12000}}, ["account_id", "plan_id"]),
                 lambda **kwargs: Revisions(self.context.read_store).review(**kwargs), True)
        self.add("memory_revision_apply", "仅凭已有可信玩家回复记录执行绑定旧版本的修订；可幂等重放，保留历史。",
                 input_schema({**account, "plan_id": text(80), "expected_id": text(80), "confirmation_id": text(80)},
                              ["account_id", "plan_id", "expected_id", "confirmation_id"]),
                 lambda **kwargs: Revisions(self.context.store).apply(**kwargs))

    def _add_memory(self):
        from companion.memory.append import MemoryAppend, KINDS
        from companion.memory.search import MemorySearch
        from companion.session.context import select_context
        self.unavailable.pop("memory_append", None)
        self.unavailable.pop("memory_search", None)
        account = {"account_id": {"type": "string", "maxLength": 80}}
        strings = lambda count=30, length=1000: {"type": "array", "maxItems": count, "items": {"type": "string", "minLength": 1, "maxLength": length}}
        properties = {**account, "record_type": {"enum": sorted(KINDS)}, "title": {"type": "string", "minLength": 1, "maxLength": 512},
                      "body": {"type": "string", "minLength": 1, "maxLength": 32000},
                      "summary": {"type": "string", "minLength": 1, "maxLength": 1500}, "topic": {"type": "string", "minLength": 1, "maxLength": 200},
                      "entities": strings(20,100), "game_version": {"type": ["string", "null"], "maxLength": 40},
                      "conditions": strings(20,1000), "evidence_ids": strings(30,80), "experiment_ids": strings(30,80),
                      "source_refs": strings(30,2000), "claim_key": {"type": "string", "maxLength": 200},
                      "fact_basis": {"enum": ["user_statement", "observed_source"]}}
        self.add("memory_append", "追加账号私有事实／偏好、讨论、假设或有条件结论；不能替换旧研究或修改账号事实。",
                 input_schema(properties, ["account_id", "record_type", "title", "body", "summary", "topic"]),
                 lambda **kwargs: MemoryAppend(self.context.store).append(**kwargs))
        search = {**account, "query": {"type": "string", "maxLength": 500}, "topic": {"type": "string", "maxLength": 200},
                  "entities": strings(20,100), "game_version": {"type": "string", "maxLength": 40}, "record_type": {"enum": sorted(KINDS)},
                  "limit": {"type": "integer", "minimum": 1, "maximum": 20}, "offset": {"type": "integer", "minimum": 0}}
        self.add("memory_search", "按账号、实体、主题和版本查询研究摘要，并附待处理冲突。",
                 input_schema(search, ["account_id"]), lambda **kwargs: MemorySearch(self.context.read_store).search(**kwargs), True)
        self.add("memory_read", "按需分页读取不可变研究正文和历史记录。",
                 input_schema({**account, "research_id": {"type": "string", "maxLength": 80}, "offset": {"type": "integer", "minimum": 0},
                               "limit": {"type": "integer", "minimum": 1, "maximum": 12000}}, ["account_id", "research_id"]),
                 lambda **kwargs: MemorySearch(self.context.read_store).read(**kwargs), True)
        self.add("memory_conflicts", "分页查看某研究的全部待处理冲突。",
                 input_schema({**account, "research_id": {"type": "string", "maxLength": 80}, "offset": {"type": "integer", "minimum": 0},
                               "limit": {"type": "integer", "minimum": 1, "maximum": 20}}, ["account_id", "research_id"]),
                 lambda **kwargs: MemorySearch(self.context.read_store).conflict_list(**kwargs), True)
        self.add("session_context", "按问题选择有版本和条件的记忆摘要，限定上下文字符预算。",
                 input_schema({**account, "query": search["query"], "game_version": search["game_version"], "entities": search["entities"],
                               "char_budget": {"type": "integer", "minimum": 500, "maximum": 12000}}, ["account_id"]),
                 lambda **kwargs: select_context(self.context.read_store, **kwargs), True)

    def _add_accounts_p2(self):
        from companion.accounts import AccountService
        from companion.accounts.refresh import AccountRefresh
        from companion.accounts.providers.enka import EnkaProvider
        from companion.resources import resource_text
        field_schema = json.loads(resource_text("schemas", "account-field.schema.json"))
        self.unavailable.pop("account_refresh", None)
        self.unavailable.pop("account_patch", None)
        account_id = {"type": "string", "maxLength": 80}
        self.add("account_refresh", "仅执行玩家本次明确导入／刷新的公开 UID 请求；记录请求引用、TTL 和差异。",
                 input_schema({"account_id": account_id, "request_ref": {"type": "string", "minLength": 1, "maxLength": 2000},
                               "purpose": {"enum": ["import", "refresh"]}}, ["account_id", "request_ref", "purpose"]),
                 lambda **kwargs: AccountRefresh(self.context.store, provider=EnkaProvider(transport=lambda url: self.context.http(url, operation="public_uid")), offline=self.context.offline).refresh(**kwargs))
        self.add("account_patch", "按预期快照版本保存玩家手工补充，保留来源并简短回显。",
                 input_schema({"account_id": account_id, "expected_snapshot_id": {"type": ["string", "null"], "maxLength": 80},
                               "fields": {"type": "array", "minItems": 1, "maxItems": 100, "items": field_schema}},
                              ["account_id", "expected_snapshot_id", "fields"]),
                 lambda **kwargs: ToolResult(data=AccountService(self.context.store).manual_update(**kwargs)))
        self.add("account_changes", "分页读取某次公开账号导入的字段差异及手工冲突，不联网。",
                 input_schema({"account_id": account_id, "query_id": {"type": "string", "maxLength": 80},
                               "offset": {"type": "integer", "minimum": 0}, "limit": {"type": "integer", "minimum": 1, "maximum": 20}},
                              ["account_id", "query_id"]),
                 lambda **kwargs: ToolResult(data=AccountService(self.context.read_store).changes(**kwargs)), True)

    def _add_sources(self):
        from companion.sources.evidence import EvidenceService
        self.unavailable.pop("source_fetch", None)
        self.unavailable.pop("evidence_register", None)
        self.add("source_fetch", "获取已选公共来源正文或带日期缓存；不查询 UID，网页仅是资料。",
                 input_schema({"url": {"type": "string", "maxLength": 2000},
                               "max_age": {"type": "integer", "minimum": 1, "maximum": 604800},
                               "force": {"type": "boolean"}, "offset": {"type": "integer", "minimum": 0},
                               "limit": {"type": "integer", "minimum": 1, "maximum": 12000}}, ["url"]),
                 lambda **kwargs: self.context.sources().fetch(offline=self.context.offline, **kwargs))
        self.add("evidence_register", "将宿主发现的资料登记到指定账号私有证据；搜索摘要不能成为正文核验。",
                 input_schema({"account_id": {"type": "string", "maxLength": 80},
                               "claim": {"type": "string", "minLength": 1, "maxLength": 500},
                               "url": {"type": "string", "maxLength": 2000},
                               "content": {"type": "string", "minLength": 1, "maxLength": 30000},
                               "kind": {"enum": ["host_search", "host_page", "manual"]},
                               "applicable_version": {"type": ["string", "null"], "maxLength": 40},
                               "stance": {"enum": ["supports", "opposes", "uncertain"]},
                               "depends_on": {"type": "array", "maxItems": 30, "items": {"type": "string", "maxLength": 80}},
                               "origin_urls": {"type": "array", "maxItems": 30, "items": {"type": "string", "maxLength": 2000}},
                               "observed_at": {"type": "string", "maxLength": 40},
                               "source_ref": {"type": "string", "maxLength": 2000}}, ["account_id", "claim", "url", "content"]),
                 lambda **kwargs: EvidenceService(self.context.store).register(**kwargs))
        self.add("evidence_resolve", "同时列出支持和反对某论点的资料及转载依赖，不投票决定真伪。",
                 input_schema({"account_id": {"type": "string", "maxLength": 80},
                               "claim": {"type": "string", "minLength": 1, "maxLength": 500},
                               "limit": {"type": "integer", "minimum": 1, "maximum": 20},
                               "offset": {"type": "integer", "minimum": 0}}, ["account_id", "claim"]),
                 lambda **kwargs: EvidenceService(self.context.read_store).resolve(**kwargs), True)

    def _add_knowledge(self):
        self.add("knowledge_search", "检索带版本与来源的中文机制知识；正式服与未上线命名空间隔离。",
                 input_schema({"query": {"type": "string", "minLength": 1, "maxLength": 500},
                               "version": {"type": "string", "maxLength": 20},
                               "namespace": {"enum": ["release", "beta", "leak"]},
                               "information_state": {"enum": ["official_verified", "official_disputed", "unknown", "stale", "beta", "leak"]},
                               "limit": {"type": "integer", "minimum": 1, "maximum": 20},
                               "offset": {"type": "integer", "minimum": 0}}, ["query"]),
                 lambda **kwargs: self.context.search().search(**kwargs), True)
        self.add("knowledge_read", "分段读取知识正文、适用条件、例外和分页来源。",
                 input_schema({"entry_id": {"type": "string", "maxLength": 80},
                               "offset": {"type": "integer", "minimum": 0}, "limit": {"type": "integer", "minimum": 1, "maximum": 12000},
                               "source_offset": {"type": "integer", "minimum": 0},
                               "source_limit": {"type": "integer", "minimum": 1, "maximum": 20}}, ["entry_id"]),
                 lambda **kwargs: self.context.search().read(**kwargs), True)

    def _add_session(self):
        from companion.accounts import AccountService
        from companion.accounts.service import REGIONS
        from companion.session import bootstrap
        from companion.resources import resource_text
        field_schema = json.loads(resource_text("schemas", "account-field.schema.json"))
        def accounts(read_only=False):
            return AccountService(self.context.read_store if read_only else self.context.store)
        account_id = {"type": "string", "pattern": "^[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}$"}
        self.add("session_bootstrap", "新会话入口：恢复本地状态，检查维护者更新，提示缺 UID／风格；从不刷新 UID。",
                 input_schema(), lambda: bootstrap(self.context))
        self.add("account_configure", "本地记录玩家提供的账号资料和 A／B 风格；UID 标为待导入，不联网。",
                 input_schema({"account_id": account_id, "label": {"type": "string", "minLength": 1, "maxLength": 100},
                    "uid": {"type": ["string", "null"], "pattern": r"^\d{9,10}$"},
                    "region": {"enum": [None, *REGIONS]}, "style": {"enum": [None, "A", "B"]},
                    "make_default": {"type": "boolean"}}, ["account_id"]),
                 lambda **kwargs: ToolResult(data=accounts().configure(**kwargs)))
        self.add("account_select", "切换默认本地账号，保留两账号独立资料。", input_schema({"account_id": account_id}, ["account_id"]),
                 lambda account_id: ToolResult(data=accounts().select(account_id)))
        self.add("account_list", "读取账号的脱敏摘要，不返回原始 UID。", input_schema(),
                 lambda: ToolResult(data={"accounts": accounts(True).list() if self.context.inspect()["account_count"] else []}), True)
        self.add("account_get", "分页读取指定本地账号资料和手工快照；不会刷新 UID。", input_schema({"account_id": account_id,
                    "cursor": {"type": ["string", "null"], "maxLength": 512},
                    "page_size": {"type": "integer", "minimum": 1, "maximum": 20}}), self.account_get, True)
        self.add("account_manual_update", "按账号保存有来源的手工字段，保留未知值与旧快照。",
                 input_schema({"account_id": account_id, "fields": {"type": "array", "minItems": 1, "maxItems": 100,
                    "items": field_schema}}, ["account_id", "fields"]),
                 lambda account_id, fields: ToolResult(data=accounts().manual_update(account_id, fields)))
        self.operations = {"session_bootstrap": self.operations.pop("session_bootstrap"), **self.operations}

    def account_get(self, account_id=None, cursor=None, page_size=10):
        from companion.accounts import AccountService
        data = AccountService(self.context.read_store).get(account_id)
        if data["snapshot"] is None:
            if cursor is not None:
                raise CompanionError(ErrorCode.INVALID_INPUT, "无快照时不可使用分页游标")
            data["next_cursor"] = None
        else:
            fields = data["snapshot"]["fields"]
            page, next_cursor = paginate(fields, cursor, page_size)
            while len(canonical(page)) > 48000 and len(page) > 1:
                page, next_cursor = paginate(fields, cursor, len(page) - 1)
            data["snapshot"] = {**data["snapshot"], "fields": page}
            data["next_cursor"] = next_cursor
        return ToolResult(data=data)

    def add(self, name, description, schema, handler, read_only=False):
        if name in self.operations:
            raise ValueError("Duplicate operation registration")
        self.operations[name] = Operation(name, description, schema, handler, read_only)

    def invoke(self, name, arguments):
        from companion.storage import SafeRoot
        from companion.storage.paths import file_lock
        try:
            if name != "program_update_apply" and self.context.data_dir.is_dir():
                with file_lock(SafeRoot(self.context.data_dir), "maintenance.lock", shared=True):
                    return self._invoke(name, arguments)
            return self._invoke(name, arguments)
        except CompanionError as error:
            return ToolResult.failure(error)
        except (OSError, ValueError, RecursionError):
            return ToolResult.failure(CompanionError(ErrorCode.INTERNAL_FAILURE, "本地访问失败，未返回个人原始资料"))

    def _invoke(self, name, arguments):
        operation = self.operations.get(name)
        if operation is None:
            return ToolResult.failure(CompanionError(ErrorCode.UNSUPPORTED, "此能力尚未实现",
                                      details={"operation": name, "owner": self.unavailable.get(name)}))
        try:
            try:
                encoded = canonical(arguments)
            except (ValueError, RecursionError) as error:
                raise CompanionError(ErrorCode.INVALID_INPUT, "参数嵌套过深或含非有限数值") from error
            if len(encoded) > 262144:
                raise CompanionError(ErrorCode.BUDGET_EXHAUSTED, "请求超过输入预算")
            errors = list(Draft202012Validator(operation.schema).iter_errors(arguments))
            if errors and name in {"simulation_compare", "mode_analyze", "comparison_save"} and isinstance(arguments, dict) and "request" in arguments:
                from companion.simulation.rotation import prepare
                prepare(arguments["request"])
            if errors and name in {"multi_team_plan", "sensitivity_analyze"} and isinstance(arguments, dict):
                from companion.experiments.contracts import check
                check("multi-team.schema.json" if name == "multi_team_plan" else "sensitivity.schema.json",
                      arguments.get("request") if name == "multi_team_plan" else arguments)
            if errors and name in {"calculate", "plan_pulls", "simulation_preflight"} and isinstance(arguments, dict) and set(arguments) == {"experiment"}:
                from companion.experiments.contracts import prepare, check
                candidate = prepare(arguments["experiment"])
                schemas = {"damage": "damage-parameters", "timeline": "timeline-parameters", "gacha": "gacha-parameters", "pull_plan": "pull-plan-parameters", "simulation": "simulation-parameters"}
                if candidate["kind"] in schemas:
                    check(schemas[candidate["kind"]] + ".schema.json", candidate["parameters"])
            if errors:
                raise CompanionError(ErrorCode.INVALID_INPUT, "工具参数不符合合同")
            result = operation.handler(**arguments)
            value = result.to_dict()
            if len(canonical(value)) > MAX_RESULT_BYTES:
                raise CompanionError(ErrorCode.BUDGET_EXHAUSTED, "工具输出超过限额；请缩小请求或分页")
            return result
        except CompanionError as error:
            return ToolResult.failure(error, missing_fields=error.details.get("fields", []) if error.code == ErrorCode.MISSING_DATA else [])
        except Exception as error:
            print("companion internal failure: " + type(error).__name__, file=sys.stderr)
            return ToolResult.failure(CompanionError(ErrorCode.INTERNAL_FAILURE, "本地操作失败，未返回个人原始资料", retryable=False))

    def doctor(self):
        checks = {"python": platform.python_version(), "supported_python": sys.version_info[:2] == (3, 12),
                  "platform": platform.system(), "sqlite": __import__("sqlite3").sqlite_version,
                  "offline": self.context.offline, "uid_network_implemented": True}
        return ToolResult(data={"checks": checks, "state": self.context.inspect()}, versions={"engine": __version__})

    def status(self):
        return ToolResult(data=self.context.inspect(), versions={"engine": __version__})

    def capabilities(self, cursor=None, page_size=20):
        entries = [{"name": name, "available": True} for name in self.operations]
        entries += [{"name": name, "available": False, "owner": owner} for name, owner in self.unavailable.items()]
        page, next_cursor = paginate(entries, cursor, page_size)
        return ToolResult(data={"items": page, "next_cursor": next_cursor})

    def updates_check(self, kind="all", force=False):
        outcomes = {}
        if kind in {"all", "knowledge"}:
            outcomes["knowledge"] = self.context.knowledge().sync(force=force, offline=self.context.offline).to_dict()
        if kind in {"all", "program"}:
            outcomes["program"] = self.context.program().check(force=force, offline=self.context.offline).to_dict()
        failed = [value for value in outcomes.values() if value["status"] != "success"]
        return ToolResult(status="partial" if failed else "success", data=outcomes,
                          warnings=["部分发布源未检查成功；请查看各项状态"] if failed else [])


def paginate(entries, cursor, page_size):
    fingerprint = hashlib.sha256(canonical(entries)).hexdigest()[:16]
    offset = 0
    if cursor is not None:
        try:
            value = json.loads(base64.urlsafe_b64decode(cursor))
            if (not isinstance(value, dict) or set(value) != {"offset", "catalog"} or value["catalog"] != fingerprint
                    or type(value["offset"]) is not int or not 0 <= value["offset"] < len(entries)):
                raise ValueError("invalid cursor")
            offset = value["offset"]
        except (ValueError, TypeError, KeyError):
            raise CompanionError(ErrorCode.INVALID_INPUT, "分页游标无效或能力表已变化")
    next_offset = offset + page_size
    next_cursor = (base64.urlsafe_b64encode(canonical({"offset": next_offset, "catalog": fingerprint})).decode()
                   if next_offset < len(entries) else None)
    return entries[offset:next_offset], next_cursor

