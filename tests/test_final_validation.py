import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
import tempfile
import pytest

def run_cmd(cmd, cwd=None, env=None):
    print(f"\n> {' '.join(float_to_str(c) if isinstance(c, float) else str(c) for c in cmd)}")
    result = subprocess.run(cmd, cwd=cwd, env=env, text=True, capture_output=True)
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    return result

def float_to_str(f):
    return f"{f:.4f}"

def test_final_validation():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        repo_path = tmp_path / "test_repo"
        repo_path.mkdir()
        
        env = os.environ.copy()
        env["PYTHONPATH"] = str(Path(__file__).parent.parent / "src")
        
        python_exe = sys.executable
        
        print("--- Initializing Repository ---")
        res = run_cmd([python_exe, "-m", "deep.cli.main", "init"], cwd=repo_path, env=env)
        assert res.returncode == 0
        assert (repo_path / ".deep").exists()
        
        print("--- Basic Workflow Test ---")
        (repo_path / "test.txt").write_text("hello deep")
        run_cmd([python_exe, "-m", "deep.cli.main", "add", "test.txt"], cwd=repo_path, env=env)
        run_cmd([python_exe, "-m", "deep.cli.main", "commit", "-m", "first"], cwd=repo_path, env=env)
        
        res = run_cmd([python_exe, "-m", "deep.cli.main", "log"], cwd=repo_path, env=env)
        assert "first" in res.stdout
        
        print("--- Integrity Check ---")
        res = run_cmd([python_exe, "-m", "deep.cli.main", "fsck"], cwd=repo_path, env=env)
        assert res.returncode == 0

if __name__ == "__main__":
    test_final_validation()
