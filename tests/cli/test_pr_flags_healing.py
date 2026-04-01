import pytest
from pathlib import Path
import subprocess
import os

def run_deep(cwd, args):
    """Run deep command and return completed process."""
    cmd = ["deep"] + args
    return subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(Path(__file__).parents[2] / "src")}
    )

@pytest.fixture
def repo(tmp_path):
    """Create a basic repository for PR tests."""
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    run_deep(repo_dir, ["init"])
    
    # Initial commit
    (repo_dir / "README.md").write_text("initial")
    run_deep(repo_dir, ["add", "."])
    run_deep(repo_dir, ["commit", "-m", "initial commit"])
    
    # Feature branch with one commit
    run_deep(repo_dir, ["branch", "feature"])
    run_deep(repo_dir, ["checkout", "feature"])
    (repo_dir / "feature.txt").write_text("feature")
    run_deep(repo_dir, ["add", "."])
    run_deep(repo_dir, ["commit", "-m", "feature commit"])
    
    # Back to main
    run_deep(repo_dir, ["checkout", "main"])
    
    return repo_dir

def test_pr_create_non_interactive(repo):
    """Test creating a PR via flags (non-interactive)."""
    res = run_deep(repo, ["pr", "create", 
                          "--title", "Test PR", 
                          "--description", "This is a test description",
                          "--head", "feature", 
                          "--base", "main"])
    assert res.returncode == 0
    assert "Local PR #1 created" in res.stdout
    assert "feature \u2192 main" in res.stdout

def test_pr_list(repo):
    """Test listing PRs."""
    run_deep(repo, ["pr", "create", "-t", "PR1", "-d", "D1", "--head", "feature", "--base", "main"])
    res = run_deep(repo, ["pr", "list"])
    assert res.returncode == 0
    assert "#1" in res.stdout
    assert "OPEN" in res.stdout
    assert "PR1" in res.stdout
    assert "PR1" in res.stdout

def test_pr_show(repo):
    """Test showing PR details."""
    run_deep(repo, ["pr", "create", "-t", "PR1", "-d", "D1", "--head", "feature", "--base", "main"])
    res = run_deep(repo, ["pr", "show", "1"])
    assert res.returncode == 0
    assert "=== Pull Request #1: PR1 ===" in res.stdout
    assert "Status:   OPEN" in res.stdout
    assert "Author:" in res.stdout
    assert "feature \u2192 main" in res.stdout
    assert "D1" in res.stdout

def test_pr_lifecycle_close_reopen(repo):
    """Test closing and reopening a PR."""
    run_deep(repo, ["pr", "create", "-t", "PR1", "-d", "D1", "--head", "feature", "--base", "main"])
    
    # Close
    res = run_deep(repo, ["pr", "close", "1"])
    assert res.returncode == 0
    assert "Pull Request #1 closed." in res.stdout
    
    # Verify status
    res = run_deep(repo, ["pr", "show", "1"])
    assert "Status:   CLOSED" in res.stdout
    
    # Reopen
    res = run_deep(repo, ["pr", "reopen", "1"])
    assert res.returncode == 0
    assert "Pull Request #1 reopened." in res.stdout
    
    # Verify status
    res = run_deep(repo, ["pr", "show", "1"])
    assert "Status:   OPEN" in res.stdout

def test_pr_merge_blocked(repo):
    """Test merging a PR when it is blocked (missing approvals)."""
    run_deep(repo, ["pr", "create", "-t", "PR1", "-d", "D1", "--head", "feature", "--base", "main"])
    
    res = run_deep(repo, ["pr", "merge", "1"])
    # By default, 1 approval is required
    assert "Merge Status: BLOCKED" in res.stdout
    assert "Approvals: 0/1" in res.stdout

def test_pr_id_validation(repo):
    """Test PR operations with invalid IDs."""
    res = run_deep(repo, ["pr", "show", "999"])
    assert res.returncode != 0
    assert "PR #999 not found locally" in res.stderr

    res = run_deep(repo, ["pr", "close", "abc"])
    assert res.returncode != 0
    assert "Failed to close PR" in res.stderr
