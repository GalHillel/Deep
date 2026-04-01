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
def sync_setup(tmp_path):
    # Remote repo
    remote_dir = tmp_path / "remote"
    remote_dir.mkdir()
    run_deep(remote_dir, ["init"])
    (remote_dir / "f1.txt").write_text("initial")
    run_deep(remote_dir, ["add", "f1.txt"])
    run_deep(remote_dir, ["commit", "-m", "Remote R1"])
    
    # Local repo
    local_dir = tmp_path / "local"
    local_dir.mkdir()
    run_deep(local_dir, ["init"])
    run_deep(local_dir, ["remote", "add", "origin", str(remote_dir)])
    
    return local_dir, remote_dir

def test_sync_default_origin(sync_setup):
    """Test sync defaults to origin."""
    local_dir, _ = sync_setup
    res = run_deep(local_dir, ["sync"])
    assert res.returncode == 0
    assert "syncing branch 'main' with 'origin'" in res.stdout
    assert (local_dir / "f1.txt").exists()

def test_sync_tracked_remote(sync_setup, tmp_path):
    """Test sync uses tracked remote for branch."""
    local_dir, _ = sync_setup
    
    # Setup second remote
    remote2 = tmp_path / "remote2"
    remote2.mkdir()
    run_deep(remote2, ["init"])
    (remote2 / "f2.txt").write_text("R2")
    run_deep(remote2, ["add", "f2.txt"])
    run_deep(remote2, ["commit", "-m", "R2 commit"])
    
    run_deep(local_dir, ["remote", "add", "upstream", str(remote2)])
    
    # Set tracking
    run_deep(local_dir, ["config", "branch.main.remote", "upstream"])
    
    res = run_deep(local_dir, ["sync"])
    assert res.returncode == 0
    assert "syncing branch 'main' with 'upstream'" in res.stdout
    assert (local_dir / "f2.txt").exists()

def test_sync_peer_override(sync_setup, tmp_path):
    """Test sync --peer overrides default/tracked remote."""
    local_dir, _ = sync_setup
    
    # Setup peer
    peer_dir = tmp_path / "peer"
    peer_dir.mkdir()
    run_deep(peer_dir, ["init"])
    (peer_dir / "p1.txt").write_text("peer data")
    run_deep(peer_dir, ["add", "p1.txt"])
    run_deep(peer_dir, ["commit", "-m", "Peer commit"])
    
    res = run_deep(local_dir, ["sync", "--peer", str(peer_dir)])
    assert res.returncode == 0
    assert f"syncing branch 'main' with '{peer_dir}'" in res.stdout
    assert (local_dir / "p1.txt").exists()

def test_sync_detached_head(sync_setup):
    """Test sync fails in detached head state."""
    local_dir, _ = sync_setup
    
    # Commit something to get a SHA
    (local_dir / "local.txt").write_text("local")
    run_deep(local_dir, ["add", "local.txt"])
    run_deep(local_dir, ["commit", "-m", "L1"])
    
    res_log = run_deep(local_dir, ["log"])
    sha = res_log.stdout.splitlines()[0].split()[1]
    
    # Detach HEAD
    run_deep(local_dir, ["checkout", sha])
    
    res = run_deep(local_dir, ["sync"])
    assert res.returncode != 0
    assert "cannot sync in detached HEAD state" in res.stderr
