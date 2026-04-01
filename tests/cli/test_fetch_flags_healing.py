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
def repo_setup(tmp_path):
    # Remote A
    remote_a = tmp_path / "remote_a"
    remote_a.mkdir()
    run_deep(remote_a, ["init"])
    (remote_a / "f1.txt").write_text("A")
    run_deep(remote_a, ["add", "f1.txt"])
    run_deep(remote_a, ["commit", "-m", "A1"])
    
    # Remote B
    remote_b = tmp_path / "remote_b"
    remote_b.mkdir()
    run_deep(remote_b, ["init"])
    (remote_b / "f2.txt").write_text("B")
    run_deep(remote_b, ["add", "f2.txt"])
    run_deep(remote_b, ["commit", "-m", "B1"])
    
    # Local repo
    local_dir = tmp_path / "local"
    local_dir.mkdir()
    run_deep(local_dir, ["init"])
    run_deep(local_dir, ["remote", "add", "origin", str(remote_a)])
    run_deep(local_dir, ["remote", "add", "upstream", str(remote_b)])
    
    return local_dir, remote_a, remote_b

def test_fetch_origin_default(repo_setup):
    """Test deep fetch (defaults to origin)."""
    local_dir, _, _ = repo_setup
    res = run_deep(local_dir, ["fetch"])
    assert res.returncode == 0
    assert "fetching from origin" in res.stdout
    
    # Verify tracking ref
    res_ref = run_deep(local_dir, ["ls-remote", "origin"])
    assert "refs/heads/main" in res_ref.stdout

def test_fetch_specific_remote(repo_setup):
    """Test deep fetch upstream."""
    local_dir, _, remote_b = repo_setup
    res = run_deep(local_dir, ["fetch", "upstream"])
    assert res.returncode == 0
    assert "fetching from upstream" in res.stdout
    
    # Verify tracking ref exists
    tracking_path = local_dir / ".deep" / "refs" / "remotes" / "upstream" / "main"
    assert tracking_path.exists()

def test_fetch_all(repo_setup):
    """Test deep fetch --all."""
    local_dir, _, _ = repo_setup
    res = run_deep(local_dir, ["fetch", "--all"])
    assert res.returncode == 0
    assert "fetching from origin" in res.stdout
    assert "fetching from upstream" in res.stdout

def test_fetch_sha(repo_setup):
    """Test deep fetch origin <sha>."""
    local_dir, remote_a, _ = repo_setup
    
    # Get a commit SHA from remote A
    res_log = run_deep(remote_a, ["log"])
    sha = res_log.stdout.splitlines()[0].split()[1] # "commit <sha>"
    
    res = run_deep(local_dir, ["fetch", "origin", sha])
    assert res.returncode == 0
    assert "fetched" in res.stdout or "already exists" in res.stdout
    
    # Verify object exists in local
    obj_path = local_dir / ".deep" / "objects" / sha[:2] / sha[2:]
    assert obj_path.exists()
