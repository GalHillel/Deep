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
    
    # Sync first commit
    run_deep(local_dir, ["pull", "origin", "main"])
    
    return local_dir, remote_dir

def test_push_basic(repo_pair):
    """Test basic fast-forward push."""
    local_dir, remote_dir = repo_pair
    
    (local_dir / "f2.txt").write_text("local change")
    run_deep(local_dir, ["add", "f2.txt"])
    run_deep(local_dir, ["commit", "-m", "Local change"])
    
    res = run_deep(local_dir, ["push", "origin", "main"])
    assert res.returncode == 0
    assert "Everything up-to-date" not in res.stdout
    
    # Verify remote has it
    res_remote = run_deep(remote_dir, ["log"])
    assert "Local change" in res_remote.stdout

def test_push_up_to_date(repo_pair):
    """Test pushing when already up-to-date."""
    local_dir, remote_dir = repo_pair
    res = run_deep(local_dir, ["push", "origin", "main"])
    assert res.returncode == 0
    assert "Everything up-to-date" in res.stdout

def test_push_force(repo_pair):
    """Test pushing with --force for non-fast-forward."""
    local_dir, remote_dir = repo_pair
    
    # Diverge remote
    (remote_dir / "f_remote.txt").write_text("remote")
    run_deep(remote_dir, ["add", "f_remote.txt"])
    run_deep(remote_dir, ["commit", "-m", "Divergent remote"])
    
    # Diverge local
    (local_dir / "f_local.txt").write_text("local")
    run_deep(local_dir, ["add", "f_local.txt"])
    run_deep(local_dir, ["commit", "-m", "Divergent local"])
    
    # Try pushing without force
    res_fail = run_deep(local_dir, ["push", "origin", "main"])
    assert res_fail.returncode != 0
    assert "rejected" in res_fail.stderr
    
    # Force push
    res_force = run_deep(local_dir, ["push", "--force", "origin", "main"])
    assert res_force.returncode == 0
    
    # Remote should now have the local commit
    res_remote = run_deep(remote_dir, ["log"])
    assert "Divergent local" in res_remote.stdout
    assert "Divergent remote" not in res_remote.stdout

def test_push_set_upstream(repo_pair):
    """Test pushing with -u."""
    local_dir, remote_dir = repo_pair
    res = run_deep(local_dir, ["push", "-u", "origin", "main"])
    assert res.returncode == 0
    
    # Check config
    res_config = run_deep(local_dir, ["config", "branch.main.remote"])
    assert res_config.stdout.strip() == "origin"

def test_push_tags(repo_pair):
    """Test pushing with --tags."""
    local_dir, remote_dir = repo_pair
    
    run_deep(local_dir, ["tag", "v1.0"])
    run_deep(local_dir, ["tag", "v2.0"])
    
    res = run_deep(local_dir, ["push", "--tags", "origin"])
    assert res.returncode == 0
    assert "Pushing refs/tags/v1.0" in res.stdout
    assert "Pushing refs/tags/v2.0" in res.stdout
    
    # Verify remote has tags
    res_remote = run_deep(remote_dir, ["tag"])
    assert "v1.0" in res_remote.stdout
    assert "v2.0" in res_remote.stdout
