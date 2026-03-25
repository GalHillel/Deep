import os
import tempfile
import subprocess
from pathlib import Path

def run_cmd(cmd, cwd):
    print(f"Running: {' '.join(cmd)}")
    res = subprocess.run(["deep"] + cmd, cwd=cwd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"FAILED: {res.stderr}")
    return res

upstream = Path(tempfile.mkdtemp())
run_cmd(["init"], upstream)
(upstream / "shared.txt").write_text("initial")
run_cmd(["add", "shared.txt"], upstream)
run_cmd(["commit", "-m", "initial"], upstream)

p1 = Path(tempfile.mkdtemp())
p2 = Path(tempfile.mkdtemp())
run_cmd(["clone", str(upstream), str(p1)], upstream)
run_cmd(["clone", str(upstream), str(p2)], upstream)

(p1 / "shared.txt").write_text("p1 edit")
run_cmd(["add", "shared.txt"], p1)
run_cmd(["commit", "-m", "p1"], p1)
run_cmd(["push"], p1)

(p2 / "shared.txt").write_text("p2 edit")
run_cmd(["add", "shared.txt"], p2)
run_cmd(["commit", "-m", "p2"], p2)

print("\n--- PULLING ---")
run_cmd(["pull"], p2)

merge_head = p2 / ".deep" / "MERGE_HEAD"
print(f"MERGE_HEAD exists? {merge_head.exists()}")
if merge_head.exists():
    print(f"MERGE_HEAD content: {merge_head.read_text()}")

print("\n--- COMMITTING ---")
(p2 / "shared.txt").write_text("resolved")
run_cmd(["add", "shared.txt"], p2)
run_cmd(["commit", "-m", "resolved"], p2)

print("\n--- CHECKING PARENTS ---")
head_file = p2 / ".deep" / "raw_head"
import json
try:
    head_sha = (p2 / ".deep" / "refs" / "heads" / "main").read_text().strip()
    data = (p2 / ".deep" / "objects" / head_sha[:2] / head_sha[2:]).read_bytes()
    import zlib
    decompressed = zlib.decompress(data)
    parts = decompressed.split(b"\x00", 1)
    content = parts[1].decode()
    print("Commit content:")
    print(content)
except Exception as e:
    print(f"Error checking parents: {e}")

print("\n--- PUSHING ---")
res = run_cmd(["push"], p2)
print(f"Push returncode: {res.returncode}")
print(f"Push output: {res.stdout}")
print(f"Push err: {res.stderr}")

import shutil
shutil.rmtree(upstream)
shutil.rmtree(p1)
shutil.rmtree(p2)
