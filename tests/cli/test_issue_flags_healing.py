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
    """Create a basic repository for Issue tests."""
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    run_deep(repo_dir, ["init"])
    return repo_dir

def test_issue_create_non_interactive(repo):
    """Test creating an issue via flags (non-interactive)."""
    res = run_deep(repo, ["issue", "create", 
                          "--title", "Bug Title", 
                          "--description", "Bug Description",
                          "--type", "bug", 
                          "--priority", "High"])
    assert res.returncode == 0
    assert "Issue #1 created locally (non-interactive)" in res.stdout
    
    # Verify via show
    res = run_deep(repo, ["issue", "show", "1"])
    assert "=== Issue #1 ===" in res.stdout
    assert "Type:     BUG" in res.stdout
    assert "Priority: High" in res.stdout
    assert "Bug Description" in res.stdout

def test_issue_list(repo):
    """Test listing issues."""
    run_deep(repo, ["issue", "create", "-t", "Issue 1", "--priority", "Low"])
    run_deep(repo, ["issue", "create", "-t", "Issue 2", "--priority", "High"])
    
    res = run_deep(repo, ["issue", "list"])
    assert res.returncode == 0
    assert "#1" in res.stdout
    assert "#2" in res.stdout
    assert "High" in res.stdout
    assert "Low" in res.stdout

def test_issue_lifecycle(repo):
    """Test closing and reopening an issue."""
    run_deep(repo, ["issue", "create", "-t", "Lifecycle Test"])
    
    # Close
    res = run_deep(repo, ["issue", "close", "1"])
    assert "Issue #1 closed" in res.stdout
    
    res = run_deep(repo, ["issue", "show", "1"])
    assert "Status:   CLOSED" in res.stdout
    
    # Reopen
    res = run_deep(repo, ["issue", "reopen", "1"])
    assert "Issue #1 reopened" in res.stdout
    
    res = run_deep(repo, ["issue", "show", "1"])
    assert "Status:   OPEN" in res.stdout

def test_issue_sync_fail_no_remote(repo):
    """Test sync fails gracefully without GitHub remote."""
    run_deep(repo, ["issue", "create", "-t", "Sync Test"])
    res = run_deep(repo, ["issue", "sync"])
    assert res.returncode != 0
    assert "Sync requires a GitHub remote" in res.stderr
