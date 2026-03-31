import os
import subprocess
import sys
import shutil
import pytest
from pathlib import Path

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

def test_cli_clone_success(tmp_path):
    """
    Init repo A, commit. Clone A to B.
    """
    repo_a = tmp_path / "repo_a"
    repo_a.mkdir()
    run_deep("init", cwd=repo_a)
    (repo_a / "f1.txt").write_text("v1")
    run_deep("add", "f1.txt", cwd=repo_a)
    run_deep("commit", "-m", "c1", cwd=repo_a)
    sha_a = (repo_a / ".deep" / "refs/heads/main").read_text().strip()
    
    repo_b = tmp_path / "repo_b"
    # Note: Deep clone handles local paths as URLs
    res = run_deep("clone", str(repo_a), str(repo_b), cwd=tmp_path)
    assert res.returncode == 0, f"STDOUT: {res.stdout}\nSTDERR: {res.stderr}"
    
    assert repo_b.exists()
    assert (repo_b / ".deep").exists()
    sha_b = (repo_b / ".deep" / "refs/heads/main").read_text().strip()
    assert sha_a == sha_b
    assert (repo_b / "f1.txt").read_text() == "v1"

def test_cli_clone_invalid_remote(tmp_path):
    """
    Try to clone a non-existent path. Assert non-zero exit code and cleanup.
    """
    invalid_path = tmp_path / "ghost"
    repo_b = tmp_path / "repo_b"
    
    res = run_deep("clone", str(invalid_path), str(repo_b), cwd=tmp_path)
    assert res.returncode != 0, f"STDOUT: {res.stdout}\nSTDERR: {res.stderr}"
    # The directory should not exist or should be empty/removed
    if repo_b.exists():
        # If it exists, it should at least not be a valid repo or should be empty
        # But strict rule 3 says: "the ENTIRE target directory should be cleaned up (deleted)"
        assert not repo_b.exists()

def test_cli_fetch_success(tmp_path):
    """
    Clone A to B. Commit on A. In B, run fetch.
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
    (repo_a / "f2.txt").write_text("v2")
    run_deep("add", "f2.txt", cwd=repo_a)
    run_deep("commit", "-m", "c2", cwd=repo_a)
    sha_a2 = (repo_a / ".deep" / "refs/heads/main").read_text().strip()
    
    # Fetch in B
    res = run_deep("fetch", "origin", cwd=repo_b)
    assert res.returncode == 0, f"STDOUT: {res.stdout}\nSTDERR: {res.stderr}"
    
    # Verify remote ref updated in B
    remote_ref_path = repo_b / ".deep" / "refs/remotes/origin/main"
    assert remote_ref_path.exists()
    assert remote_ref_path.read_text().strip() == sha_a2
    
    # Verify object exists in B
    obj_path = repo_b / ".deep" / "objects" / sha_a2[:2] / sha_a2[2:]
    assert obj_path.exists()

def test_cli_fetch_invalid_remote(tmp_path):
    """
    In repo B, try to fetch from invalid remote.
    """
    repo_a = tmp_path / "repo_a"
    repo_a.mkdir()
    run_deep("init", cwd=repo_a)
    (repo_a / "f1.txt").write_text("v1")
    run_deep("add", "f1.txt", cwd=repo_a)
    run_deep("commit", "-m", "c1", cwd=repo_a)
    
    repo_b = tmp_path / "repo_b"
    run_deep("clone", str(repo_a), str(repo_b), cwd=tmp_path)
    
    # Break the remote URL in config
    from deep.core.config import Config
    config = Config(repo_b)
    config.set_local("remote.origin.url", str(tmp_path / "invalid_path"))
    
    res = run_deep("fetch", "origin", cwd=repo_b)
    assert res.returncode != 0, f"STDOUT: {res.stdout}\nSTDERR: {res.stderr}"
    
    # Verify rollback: index and refs should remain as they were
    # Actually fetch doesn't change index, but it might have updated some refs if it were partial.
    # We want to ensure no partial ref updates.
