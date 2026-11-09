"""Dependency-free, single-tool stdio MCP probe for isolated P0 workspaces."""
from __future__ import annotations

import json
import sys

VERSION = "0.1.0-p0"
PROTOCOLS = {"2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25"}
TOOL = {"name": "probe_status", "description": "Return the fixed P0 probe version and text; no network or account access.",
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}}


def serve():
    initialized = False
    for line in sys.stdin:
        request = None
        try:
            request = json.loads(line)
            if not isinstance(request, dict) or request.get("jsonrpc") != "2.0" or not isinstance(request.get("method"), str):
                raise ValueError("Invalid JSON-RPC request")
            if "id" not in request:
                if request["method"] == "notifications/initialized":
                    initialized = True
                continue
            method, params = request["method"], request.get("params", {})
            if not isinstance(params, dict):
                response = {"error": {"code": -32602, "message": "Invalid params"}}
            elif method == "initialize":
                protocol = params.get("protocolVersion")
                response = {"result": {"protocolVersion": protocol if protocol in PROTOCOLS else "2025-11-25",
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "hsr-companion-p0-probe", "version": VERSION},
                    "instructions": "P0 validation only. probe_status returns fixed text and version; it never accesses accounts or the network."}}
            elif method == "ping":
                response = {"result": {}}
            elif not initialized:
                response = {"error": {"code": -32002, "message": "Send notifications/initialized first"}}
            elif method == "tools/list":
                response = {"result": {"tools": [TOOL]}}
            elif method == "tools/call":
                if params.get("name") != "probe_status" or params.get("arguments", {}) != {}:
                    response = {"error": {"code": -32602, "message": "Only probe_status with empty arguments is supported"}}
                else:
                    response = {"result": {"content": [{"type": "text", "text": json.dumps(
                        {"version": VERSION, "text": "星穹铁道 P0 探针可用"}, ensure_ascii=False)}], "isError": False}}
            else:
                response = {"error": {"code": -32601, "message": "Method not found"}}
            response.update(jsonrpc="2.0", id=request["id"])
        except (ValueError, TypeError) as exc:
            response = {"jsonrpc": "2.0", "id": request.get("id") if isinstance(request, dict) else None,
                        "error": {"code": -32700 if isinstance(exc, json.JSONDecodeError) else -32600,
                                  "message": "Parse error" if isinstance(exc, json.JSONDecodeError) else "Invalid request"}}
        sys.stdout.write(json.dumps(response, ensure_ascii=False)+"\n")
        sys.stdout.flush()


if __name__ == "__main__":
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    serve()
