import os
import subprocess
import pytest
from pathlib import Path

def run_deep(repo_dir, args):
    """Run a deep command and return the output."""
    result = subprocess.run(
        ["deep"] + args,
        cwd=repo_dir,
        capture_output=True,
        text=True
    )
    return result

@pytest.fixture
def repo(tmp_path):
    """Create a fresh deep repository."""
    repo_dir = tmp_path / "test_repo"
    repo_dir.mkdir()
    run_deep(repo_dir, ["init"])
    return repo_dir

def test_status_basic(repo):
    """Test standard human-readable status."""
    (repo / "file.txt").write_text("hello")
    run_deep(repo, ["add", "file.txt"])
    (repo / "modified.txt").write_text("original")
    run_deep(repo, ["add", "modified.txt"])
    run_deep(repo, ["commit", "-m", "initial"])
    
    (repo / "modified.txt").write_text("updated")
    (repo / "untracked.txt").write_text("new")
    
    res = run_deep(repo, ["status"])
    assert "On branch main" in res.stdout
    assert "modified:   modified.txt" in res.stdout
    assert "untracked.txt" in res.stdout

def test_status_porcelain(repo):
    """Test machine-readable porcelain status."""
    (repo / "modified.txt").write_text("original")
    run_deep(repo, ["add", "modified.txt"])
    run_deep(repo, ["commit", "-m", "initial"])

    (repo / "staged.txt").write_text("staged")
    run_deep(repo, ["add", "staged.txt"])
    
    (repo / "modified.txt").write_text("updated")
    
    (repo / "untracked.txt").write_text("new")
    
    res = run_deep(repo, ["status", "--porcelain"])
    
    # Porcelain should NOT have "On branch main"
    assert "On branch main" not in res.stdout
    
    lines = res.stdout.strip().split("\n")
    assert "A  staged.txt" in lines
    assert " M modified.txt" in lines
    assert "?? untracked.txt" in lines

def test_status_verbose(repo):
    """Test verbose status showing staged diff."""
    (repo / "file.txt").write_text("line 1\n")
    run_deep(repo, ["add", "file.txt"])
    run_deep(repo, ["commit", "-m", "initial"])
    
    (repo / "file.txt").write_text("line 1\nline 2\n")
    run_deep(repo, ["add", "file.txt"])
    
    res = run_deep(repo, ["status", "--verbose"])
    assert "Changes to be committed (diff):" in res.stdout
    assert "diff --deep a/file.txt b/file.txt" in res.stdout
    assert "+line 2" in res.stdout

def test_status_clean(repo):
    """Test status in a clean repository."""
    res = run_deep(repo, ["status"])
    assert "nothing to commit, working tree clean" in res.stdout
