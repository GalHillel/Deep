import subprocess
import pytest
from pathlib import Path

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
    # Remote repo
    remote_dir = tmp_path / "remote"
    remote_dir.mkdir()
    run_deep(remote_dir, ["init"])
    (remote_dir / "f1.txt").write_text("v1")
    run_deep(remote_dir, ["add", "f1.txt"])
    run_deep(remote_dir, ["commit", "-m", "R1"])
    run_deep(remote_dir, ["tag", "v1.0"])
    
    # Get full SHA for validation
    res = run_deep(remote_dir, ["log", "-n", "1"])
    # log output starts with "commit <sha>"
    sha = res.stdout.splitlines()[0].split()[1]
    
    return remote_dir, sha

def test_ls_remote_local(repo_setup):
    """Test ls-remote against a local path."""
    remote_dir, sha = repo_setup
    
    # We can run it from anywhere
    res = run_deep(remote_dir.parent, ["ls-remote", str(remote_dir)])
    assert res.returncode == 0
    assert f"{sha}\tHEAD" in res.stdout
    assert f"{sha}\trefs/heads/main" in res.stdout
    assert f"{sha}\trefs/tags/v1.0" in res.stdout

def test_ls_remote_alias(repo_setup, tmp_path):
    """Test ls-remote using a remote alias (origin)."""
    remote_dir, sha = repo_setup
    
    local_dir = tmp_path / "local"
    local_dir.mkdir()
    run_deep(local_dir, ["init"])
    run_deep(local_dir, ["remote", "add", "origin", str(remote_dir)])
    
    res = run_deep(local_dir, ["ls-remote", "origin"])
    assert res.returncode == 0
    assert f"{sha}\tHEAD" in res.stdout
    assert f"{sha}\trefs/heads/main" in res.stdout

def test_ls_remote_invalid_url(tmp_path):
    """Test ls-remote with an invalid URL."""
    res = run_deep(tmp_path, ["ls-remote", "non-existent-remote"])
    assert res.returncode != 0
    assert "ls-remote failed" in res.stderr
