import subprocess
import pytest
from pathlib import Path
import os
import shutil

def run_deep(repo_dir, args):
    """Run a deep command and return the result."""
    result = subprocess.run(
        ["deep"] + args,
        cwd=repo_dir,
        capture_output=True,
        text=True
    )
    return result

@pytest.fixture
def repo_pair(tmp_path):
    # Remote repo
    remote_dir = tmp_path / "remote_repo"
    remote_dir.mkdir()
    run_deep(remote_dir, ["init"])
    (remote_dir / "f1.txt").write_text("initial")
    run_deep(remote_dir, ["add", "f1.txt"])
    run_deep(remote_dir, ["commit", "-m", "Remote initial"])
    
    # Local repo
    local_dir = tmp_path / "local_repo"
    local_dir.mkdir()
    run_deep(local_dir, ["init"])
    run_deep(local_dir, ["remote", "add", "origin", str(remote_dir)])
    
    return local_dir, remote_dir

def test_pull_empty_ff(repo_pair):
    """Test pulling into an empty repository (fast-forward)."""
    local_dir, remote_dir = repo_pair
    res = run_deep(local_dir, ["pull", "origin", "main"])
    assert res.returncode == 0
    assert "Fast-forwarding" in res.stdout
    assert (local_dir / "f1.txt").exists()

def test_pull_merge(repo_pair):
    """Test pulling with a merge (divergent history)."""
    local_dir, remote_dir = repo_pair
    
    # Init local
    run_deep(local_dir, ["pull", "origin", "main"])
    
    # Diverge remote
    (remote_dir / "f_remote.txt").write_text("remote")
    run_deep(remote_dir, ["add", "f_remote.txt"])
    run_deep(remote_dir, ["commit", "-m", "Remote change"])
    
    # Diverge local
    (local_dir / "f_local.txt").write_text("local")
    run_deep(local_dir, ["add", "f_local.txt"])
    run_deep(local_dir, ["commit", "-m", "Local change"])
    
    res = run_deep(local_dir, ["pull", "origin", "main"])
    assert res.returncode == 0
    assert "Merging" in res.stdout
    
    # Verify merge commit
    res_log = run_deep(local_dir, ["log"])
    assert "Merge" in res_log.stdout

def test_pull_rebase(repo_pair):
    """Test pulling with --rebase."""
    local_dir, remote_dir = repo_pair
    
    # Init local
    run_deep(local_dir, ["pull", "origin", "main"])
    
    # Diverge remote
    (remote_dir / "f_remote.txt").write_text("remote")
    run_deep(remote_dir, ["add", "f_remote.txt"])
    run_deep(remote_dir, ["commit", "-m", "Remote change"])
    
    # Diverge local
    (local_dir / "f_local.txt").write_text("local")
    run_deep(local_dir, ["add", "f_local.txt"])
    run_deep(local_dir, ["commit", "-m", "Local change"])
    
    res = run_deep(local_dir, ["pull", "--rebase", "origin", "main"])
    assert res.returncode == 0
    assert "Rebasing" in res.stdout
    
    # Verify linear history (no merge commit)
    res_log = run_deep(local_dir, ["log"])
    assert "Merge" not in res_log.stdout
    assert "Local change" in res_log.stdout
    assert "Remote change" in res_log.stdout

def test_pull_up_to_date(repo_pair):
    """Test pulling when already up to date."""
    local_dir, remote_dir = repo_pair
    run_deep(local_dir, ["pull", "origin", "main"])
    
    res = run_deep(local_dir, ["pull", "origin", "main"])
    assert res.returncode == 0
    assert "Already up to date" in res.stdout
