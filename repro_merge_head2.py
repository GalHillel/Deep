import subprocess
import os
from pathlib import Path

def run_deep(args, cwd):
    cmd = ["deep"] + args
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return result

tmp = Path("C:/Users/galh2/AppData/Local/Temp/deep_test_dir").resolve()
if tmp.exists():
    import shutil
    shutil.rmtree(tmp, ignore_errors=True)
tmp.mkdir(parents=True, exist_ok=True)

upstream = tmp / "upstream"
p1 = tmp / "p1"
p2 = tmp / "p2"

upstream.mkdir()
run_deep(["init"], cwd=upstream)
(upstream / "shared.txt").write_text("initial")
run_deep(["add", "shared.txt"], cwd=upstream)
run_deep(["commit", "-m", "initial"], cwd=upstream)

run_deep(["clone", str(upstream), str(p1)], cwd=tmp)
run_deep(["clone", str(upstream), str(p2)], cwd=tmp)

(p1 / "shared.txt").write_text("p1 edit")
run_deep(["add", "shared.txt"], cwd=p1)
run_deep(["commit", "-m", "p1"], cwd=p1)
run_deep(["push"], cwd=p1)

(p2 / "shared.txt").write_text("p2 edit")
run_deep(["add", "shared.txt"], cwd=p2)
run_deep(["commit", "-m", "p2"], cwd=p2)

print("Running pull on p2")
res = run_deep(["pull"], cwd=p2)
print("STDOUT:", res.stdout)
print("STDERR:", res.stderr)
print("RC:", res.returncode)

m = p2 / ".deep" / "MERGE_HEAD"
print("MERGE_HEAD EXISTS:", m.exists())
