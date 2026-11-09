"""Bounded sequential JSON-RPC stdio; stdout contains protocol messages only."""
from collections import OrderedDict
import json
import sys

from companion import __version__
from companion.contracts import CompanionError, canonical
from companion.services.registry import paginate

PROTOCOLS = {"2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25"}
MAX_INPUT = 262144


def serve(registry, stdin=None, stdout=None):
    stdin, stdout = stdin or sys.stdin, stdout or sys.stdout
    if hasattr(stdin, "reconfigure"):
        stdin.reconfigure(encoding="utf-8")
    if hasattr(stdout, "reconfigure"):
        stdout.reconfigure(encoding="utf-8")
    handshake = ready = False
    cache = OrderedDict()

    def fail(code, message):
        return {"error": {"code": code, "message": message}}

    while True:
        line = stdin.readline(MAX_INPUT + 1)
        if not line:
            return 0
        request_id = None
        try:
            if len(line.encode("utf-8")) > MAX_INPUT:
                while line and not line.endswith("\n"):
                    line = stdin.readline(MAX_INPUT + 1)
                response = fail(-32600, "Request exceeds input budget")
            else:
                from companion.knowledge.package import unique_object
                request = json.loads(line, object_pairs_hook=unique_object)
                if (not isinstance(request, dict) or request.get("jsonrpc") != "2.0" or
                        not isinstance(request.get("method"), str) or
                        ("id" in request and type(request["id"]) not in (int, str))):
                    response = fail(-32600, "Invalid request")
                else:
                    request_id = request.get("id")
                    method, params = request["method"], request.get("params", {})
                    if "id" not in request:
                        if method == "notifications/initialized" and handshake:
                            ready = True
                        continue
                    key, encoded = canonical(request_id), canonical(request)
                    if key in cache:
                        old_request, old_response = cache[key]
                        response = old_response if old_request == encoded else fail(-32600, "Request ID already used")
                    elif not isinstance(params, dict):
                        response = fail(-32602, "Invalid params")
                    elif method == "initialize":
                        if handshake or not isinstance(params.get("protocolVersion"), str):
                            response = fail(-32602, "Invalid initialization")
                        else:
                            handshake = True
                            response = {"result": {"protocolVersion": params["protocolVersion"] if params["protocolVersion"] in PROTOCOLS else "2025-11-25",
                                "capabilities": {"tools": {"listChanged": False}},
                                "serverInfo": {"name": "hsr-companion", "version": __version__},
                                "instructions": "新会话先调用 session_bootstrap；按账号、版本检索知识和个人研究。知识自动同步，程序只提示，UID 仅在玩家明确要求时导入。calculate支持固定状态、局部时序、抽取DP；plan_pulls支持预算规划。四模式先mode_select／analysis_schema，再mode_analyze或simulation_compare；multi_team_plan检查资源，sensitivity_analyze返回反转条件，comparison_save／experiment_replay保存重算。仅简化窗口和清单内指定动作，缺关键机制不排名；当前期数须有区服排期证据，不编分数、必胜或账号收益；研究冲突等待玩家确认。"}}
                    elif method == "ping":
                        response = {"result": {}}
                    elif not ready:
                        response = fail(-32002, "Initialize and send notifications/initialized first")
                    elif method == "tools/list":
                        if set(params) - {"cursor", "_meta"}:
                            response = fail(-32602, "Invalid list params")
                        else:
                            tools = [operation.tool() for operation in registry.operations.values()]
                            items, cursor = paginate(tools, params.get("cursor"), 5)
                            response = {"result": {"tools": items, **({"nextCursor": cursor} if cursor else {})}}
                    elif method == "tools/call":
                        if (set(params) - {"name", "arguments", "_meta"} or not isinstance(params.get("name"), str)
                                or not isinstance(params.get("arguments", {}), dict)):
                            response = fail(-32602, "Invalid tool call params")
                        else:
                            result = registry.invoke(params["name"], params.get("arguments", {}))
                            value = result.to_dict()
                            response = {"result": {"content": [{"type": "text", "text": canonical(value).decode()}],
                                                   "isError": result.status == "error", "structuredContent": value}}
                    else:
                        response = fail(-32601, "Method not found")
                    if key not in cache:
                        cache[key] = (encoded, response)
                        if len(cache) > 128:
                            cache.popitem(last=False)
        except json.JSONDecodeError:
            response = fail(-32700, "Parse error")
        except CompanionError:
            response = fail(-32602, "Invalid params")
        except (ValueError, TypeError, RecursionError):
            response = fail(-32600, "Invalid request")
        stdout.write(canonical({"jsonrpc": "2.0", "id": request_id, **response}).decode() + "\n")
        stdout.flush()

