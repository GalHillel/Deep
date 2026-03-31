import os
import subprocess
import sys
from pathlib import Path
import pytest

def run_deep(*args, cwd=None):
    # Ensure PYTHONPATH is set to include the src directory
    env = os.environ.copy()
    src_path = str(Path.cwd() / "src")
    if "PYTHONPATH" in env:
        env["PYTHONPATH"] = f"{src_path}{os.pathsep}{env['PYTHONPATH']}"
    else:
        env["PYTHONPATH"] = src_path
        
    return subprocess.run(
        [sys.executable, "-m", "deep.cli.main", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        env=env
    )

def test_cli_pull_success(tmp_path):
    """
    Setup A and B. Modify A. Pull in B.
    """
    repo_a = tmp_path / "repo_a"
    repo_a.mkdir()
    run_deep("init", cwd=repo_a)
    (repo_a / "f1.txt").write_text("v1")
    run_deep("add", "f1.txt", cwd=repo_a)
    run_deep("commit", "-m", "c1", cwd=repo_a)
    
    repo_b = tmp_path / "repo_b"
    run_deep("clone", str(repo_a), str(repo_b), cwd=tmp_path)
    
    # New commit on A
    (repo_a / "f1.txt").write_text("v2")
    run_deep("add", "f1.txt", cwd=repo_a)
    run_deep("commit", "-m", "c2", cwd=repo_a)
    sha_a2 = (repo_a / ".deep" / "refs/heads/main").read_text().strip()
    
    # Pull in B
    res = run_deep("pull", "origin", "main", cwd=repo_b)
    assert res.returncode == 0, f"STDOUT: {res.stdout}\nSTDERR: {res.stderr}"
    
    assert (repo_b / "f1.txt").read_text() == "v2"
    sha_b = (repo_b / ".deep" / "refs/heads/main").read_text().strip()
    assert sha_b == sha_a2
    
    # Verify tracking ref
    tracking_ref = repo_b / ".deep" / "refs/remotes/origin/main"
    assert tracking_ref.read_text().strip() == sha_a2

def test_cli_pull_physical_verify(tmp_path):
    """
    BUG 2 FIX: Pull should re-fetch if object is missing despite ref matching.
    """
    repo_a = tmp_path / "repo_a"
    repo_a.mkdir()
    run_deep("init", cwd=repo_a)
    (repo_a / "f1.txt").write_text("v1")
    run_deep("add", "f1.txt", cwd=repo_a)
    run_deep("commit", "-m", "c1", cwd=repo_a)
    sha_a = (repo_a / ".deep" / "refs/heads/main").read_text().strip()
    
    repo_b = tmp_path / "repo_b"
    run_deep("clone", str(repo_a), str(repo_b), cwd=tmp_path)
    
    # Manually delete the object for the current commit in B
    obj_path = repo_b / ".deep" / "objects" / sha_a[:2] / sha_a[2:]
    assert obj_path.exists()
    obj_path.unlink()
    
    # Pull in B. It should see object is missing and re-fetch.
    res = run_deep("pull", "origin", "main", cwd=repo_b)
    assert res.returncode == 0, f"STDOUT: {res.stdout}\nSTDERR: {res.stderr}"
    
    # Object should be back
    assert obj_path.exists()

def test_cli_push_success(tmp_path):
    """
    Setup A and B. Commit in B. Push to A.
    """
    # Repo A is the "server" (must be bare for normal git, but Deep handles both)
    repo_a = tmp_path / "repo_a"
    repo_a.mkdir()
    run_deep("init", cwd=repo_a)
    (repo_a / "f1.txt").write_text("v1")
    run_deep("add", "f1.txt", cwd=repo_a)
    run_deep("commit", "-m", "c1", cwd=repo_a)
    
    repo_b = tmp_path / "repo_b"
    run_deep("clone", str(repo_a), str(repo_b), cwd=tmp_path)
    
    # New commit in B
    (repo_b / "f2.txt").write_text("v2")
    run_deep("add", "f2.txt", cwd=repo_b)
    run_deep("commit", "-m", "c2", cwd=repo_b)
    sha_b2 = (repo_b / ".deep" / "refs/heads/main").read_text().strip()
    
    # Push from B to A
    res = run_deep("push", "origin", "main", cwd=repo_b)
    assert res.returncode == 0, f"STDOUT: {res.stdout}\nSTDERR: {res.stderr}"
    
    # Verify A has the commit
    sha_a = (repo_a / ".deep" / "refs/heads/main").read_text().strip()
    assert sha_a == sha_b2
    
    # Verify B updated tracking ref
    tracking_ref = repo_b / ".deep" / "refs/remotes/origin/main"
    assert tracking_ref.read_text().strip() == sha_b2

def test_cli_push_rejected(tmp_path):
    """
    Transactional Push: If push is rejected (e.g. non-ff), tracking ref should NOT update.
    """
    repo_a = tmp_path / "repo_a"
    repo_a.mkdir()
    run_deep("init", cwd=repo_a)
    (repo_a / "f1.txt").write_text("v1")
    run_deep("add", "f1.txt", cwd=repo_a)
    run_deep("commit", "-m", "c1", cwd=repo_a)
    sha_a1 = (repo_a / ".deep" / "refs/heads/main").read_text().strip()

    repo_b = tmp_path / "repo_b"
    run_deep("clone", str(repo_a), str(repo_b), cwd=tmp_path)
    
    # Diverge A
    (repo_a / "f-a.txt").write_text("a")
    run_deep("add", "f-a.txt", cwd=repo_a)
    run_deep("commit", "-m", "c-a", cwd=repo_a)
    sha_a2 = (repo_a / ".deep" / "refs/heads/main").read_text().strip()
    
    # Diverge B
    (repo_b / "f-b.txt").write_text("b")
    run_deep("add", "f-b.txt", cwd=repo_b)
    run_deep("commit", "-m", "c-b", cwd=repo_b)
    sha_b2 = (repo_b / ".deep" / "refs/heads/main").read_text().strip()
    
    # Push from B to A (should be rejected as non-ff)
    res = run_deep("push", "origin", "main", cwd=repo_b)
    assert res.returncode != 0
    
    # Tracking ref in B should still point to a1, not b2
    tracking_ref = repo_b / ".deep" / "refs/remotes/origin/main"
    assert tracking_ref.read_text().strip() == sha_a1
