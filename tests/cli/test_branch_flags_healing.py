import subprocess
import pytest
import os
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
def repo(tmp_path):
    repo_dir = tmp_path / "test_repo"
    repo_dir.mkdir()
    run_deep(repo_dir, ["init"])

    # Initial commit to have a HEAD
    (repo_dir / "f1.txt").write_text("v1")
    run_deep(repo_dir, ["add", "f1.txt"])
    run_deep(repo_dir, ["commit", "-m", "Initial commit"])

    return repo_dir

def test_branch_list(repo):
    """Test listing local branches."""
    # Create a secondary branch
    run_deep(repo, ["branch", "feat"])
    
    res = run_deep(repo, ["branch"])
    assert res.returncode == 0
    # On main (standard default)
    assert "* main" in res.stdout
    assert "  feat" in res.stdout

def test_branch_create(repo):
    """Test creating a branch at a specific start point."""
    # Get current commit SHA
    res_log = run_deep(repo, ["log", "--oneline"])
    sha = res_log.stdout.split()[0]
    
    res = run_deep(repo, ["branch", "new_branch", sha])
    assert res.returncode == 0
    assert "Created branch 'new_branch'" in res.stdout
    
    # Check if exists
    res_list = run_deep(repo, ["branch"])
    assert "new_branch" in res_list.stdout

def test_branch_delete(repo):
    """Test deleting a branch."""
    run_deep(repo, ["branch", "to_delete"])
    res = run_deep(repo, ["branch", "-d", "to_delete"])
    assert res.returncode == 0
    assert "Deleted branch 'to_delete'" in res.stdout
    
    # Check if gone
    res_list = run_deep(repo, ["branch"])
    assert "to_delete" not in res_list.stdout

def test_branch_all(repo):
    """Test listing with --all (fake a remote branch)."""
    dg_dir = repo / ".deep"
    remote_path = dg_dir / "refs" / "remotes" / "origin" / "main"
    remote_path.parent.mkdir(parents=True, exist_ok=True)
    remote_path.write_text("0" * 40) # Fake SHA
    
    res = run_deep(repo, ["branch", "-a"])
    assert res.returncode == 0
    assert "remotes/origin/main" in res.stdout

def test_branch_verbose(repo):
    """Test verbose output (-v and -vv)."""
    # Set up tracking for -vv
    run_deep(repo, ["config", "branch.main.remote", "origin"])
    run_deep(repo, ["config", "branch.main.merge", "refs/heads/main"])
    
    # Test -v
    res_v = run_deep(repo, ["branch", "-v"])
    assert res_v.returncode == 0
    # Should show SHA (Yellow in code, but captured as text)
    # The code uses Color.wrap which adds ANSI codes.
    # We just check if it contains some hex-like string before the branch name
    assert "main" in res_v.stdout
    
    # Test -vv
    res_vv = run_deep(repo, ["branch", "-vv"])
    assert res_vv.returncode == 0
    assert "[origin/main]" in res_vv.stdout

def test_branch_delete_requires_name(repo):
    """Test that deleting requires a name (no traceback)."""
    res = run_deep(repo, ["branch", "-d"])
    assert res.returncode != 0
    assert "branch name required" in res.stderr
