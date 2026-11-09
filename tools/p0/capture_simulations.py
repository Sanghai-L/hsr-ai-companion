from common import ROOT, LOCAL, command

if __name__ == "__main__":
    python=LOCAL/"probes/hsr-nous/中文 空格验证/Scripts/python.exe"
    result=command([python,ROOT/"tools/p0/run_simulations.py"],task="D008",name="two-team-runs",timeout=120)
    print(result['stdout'][-6000:])
    print(result['stderr'][-1800:])
    raise SystemExit(result['exit_code'] if result['exit_code'] is not None else 4)
