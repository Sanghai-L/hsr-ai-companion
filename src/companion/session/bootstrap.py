"""Restartable onboarding; update checks never imply an account network refresh."""
from companion.accounts import AccountService
from companion.contracts import CompanionError, ToolResult


def bootstrap(context):
    store = context.store
    accounts = AccountService(store)
    state = context.inspect()
    questions, missing = [], []
    selected = None
    if state["default_account_id"]:
        selected = store.require_account(state["default_account_id"])
    if selected is None:
        missing.append("account")
        questions.append({"field": "account", "prompt": "请提供要记录的账号 UID 与区服；也可先手工补充资料。"})
    else:
        for field, prompt in (("uid", "请提供此账号的 UID；只有明确要求导入时才查询公开展示。"),
                              ("region", "请选择此账号区服。")):
            if selected[field] is None:
                missing.append(field)
                questions.append({"field": field, "prompt": prompt})
    if selected is None or selected["style"] is None:
        missing.append("style")
        questions.append({"field": "style", "prompt": "请选择回答风格，之后可以更改。",
                          "options": [{"value": "A", "label": "自然交流型"}, {"value": "B", "label": "专业分析型"}]})
    recovery = store.recover_research()
    checks = {}
    for name, action in (("knowledge", lambda: context.knowledge().sync(offline=context.offline)),
                         ("program", lambda: context.program().check(offline=context.offline))):
        try:
            checks[name] = action().to_dict()
        except CompanionError as error:
            checks[name] = ToolResult.failure(error).to_dict()
    warnings = ["启动只恢复本地账号，不查询 UID；公开展示仅在玩家明确要求时导入或刷新"]
    if any(value["status"] != "success" for value in checks.values()):
        warnings.append("部分维护者发布源未核验；未宣称程序或知识最新")
    if recovery["damaged"] or recovery["missing"]:
        warnings.append("个人研究存在损坏或丢失文件，请检查本地恢复报告")
    memory = None
    if selected:
        from companion.session.context import select_context
        try:
            memory = select_context(store, selected["id"], char_budget=3000).to_dict()
        except CompanionError as error:
            memory = ToolResult.failure(error).to_dict()
            warnings.append("部分个人记忆不可读取；保留原文件并查看恢复报告")
    return ToolResult(status="partial" if missing or any(v["status"] != "success" for v in checks.values()) else "success",
        data={"state": state, "questions": questions, "updates": checks, "recovery": recovery, "memory": memory,
              "uid_import": accounts.import_state(selected["id"], selected) if selected else "missing_uid",
              "uid_refreshed": False, "program_installed": False}, missing_fields=missing, warnings=warnings)

