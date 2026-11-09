"""D008 entry: log real commands; stop on test failures before simulation."""
from common import ROOT, LOCAL, command, update_task


def main():
    update_task("D008", "IN_PROGRESS", summary="核心最小依赖已装；开始离线核心测试与两队真实输入验证",
                next_step="核心回归、场景组装、事件抽查与同种子复放", level="上游真实代码；未作游戏精度认证")
    python = LOCAL / "probes/hsr-nous/中文 空格验证/Scripts/python.exe"
    result = command([python, ROOT/"tools/p0/run_core_tests.py"], task="D008", name="core-tests", timeout=150)
    print(result["stdout"][-3500:])
    print(result["stderr"][-1500:])
    raise SystemExit(result["exit_code"] if result["exit_code"] is not None else 4)


if __name__ == "__main__":
    main()
