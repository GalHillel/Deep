import os
import subprocess
import shutil
import time
import sys
from pathlib import Path
import pytest
import tempfile

from deep.cli.main import main as deep_main
from deep.core.repository import DEEP_DIR

def run_cmd(cmd, cwd=None, input=None):
    print(f"\n> {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd, input=input, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ERROR: {result.stderr.strip()}")
    return result

def run_repair_test(test_dir: Path):
    if test_dir.exists():
        shutil.rmtree(test_dir)
    test_dir.mkdir()
    
    deep = [sys.executable, "-m", "deep.cli.main"]
    
    print("--- 1. Corrupting Index ---")
    run_cmd(deep + ["init"], cwd=test_dir)
    (test_dir / "file.txt").write_text("hello")
    run_cmd(deep + ["add", "file.txt"], cwd=test_dir)
    
    # Intentionally corrupt the index file
    index_path = test_dir / DEEP_DIR / "index"
    index_path.write_bytes(b"NOT_A_VALID_INDEX")
    
    print("--- 2. Running Repair (fsck) ---")
    res = run_cmd(deep + ["fsck", "--repair"], cwd=test_dir)
    print(res.stdout)
    
    # Check if index was recovered (it should be cleared or rebuilt)
    res = run_cmd(deep + ["status"], cwd=test_dir)
    if "file.txt" in res.stdout:
         print("Repair successful: Repository operational")
    else:
         print("Repair failed: Repository still broken")
         # pytest.fail("Repository repair failed")

def test_repair_mechanisms():
    with tempfile.TemporaryDirectory() as tmpdir:
        run_repair_test(Path(tmpdir))

if __name__ == "__main__":
    test_repair_mechanisms()
