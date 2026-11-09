from common import ROOT, LOCAL, command

if __name__=="__main__":
    python=LOCAL/"probes/hsr-nous/中文 空格验证/Scripts/python.exe"
    record=command([python,"-m","pytest",ROOT/"tests/p0/test_simulator_budget.py","-q","-ra",
                    "-o","cache_dir="+str(LOCAL/"cache/pytest/budget")],task="D008",name="budget-regression",timeout=30)
    print(record['stdout'][-2200:])
    print(record['stderr'][-600:])
    raise SystemExit(record['exit_code'] if record['exit_code'] is not None else 4)
