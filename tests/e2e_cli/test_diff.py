import pytest
from pathlib import Path

def test_diff_working_staged_commit(repo_factory):
    """Test diff in various states (working, staged, branch)."""
    path = repo_factory.create()
    f = path / "file.txt"
    f.write_text("v1")
    repo_factory.run(["add", "file.txt"], cwd=path)
    repo_factory.run(["commit", "-m", "v1"], cwd=path)
    
    # 1. Working tree vs HEAD
    f.write_text("v1-edit")
    res = repo_factory.run(["diff"], cwd=path)
    assert "-v1" in res.stdout
    assert "+v1-edit" in res.stdout
    
    # 2. Staged changes (--staged or --cached)
    repo_factory.run(["add", "file.txt"], cwd=path)
    res = repo_factory.run(["diff", "--staged"], cwd=path)
    assert "+v1-edit" in res.stdout
    
    # 3. Diff between commits
    repo_factory.run(["commit", "-m", "v2"], cwd=path)
    res = repo_factory.run(["diff", "HEAD~1", "HEAD"], cwd=path)
    assert "+v1-edit" in res.stdout

def test_show_commit(repo_factory):
    """Test deep show [sha] functionality."""
    path = repo_factory.create()
    (path / "f.txt").write_text("initial")
    repo_factory.run(["add", "f.txt"], cwd=path)
    repo_factory.run(["commit", "-m", "initial"], cwd=path)
    
    res = repo_factory.run(["log", "-n", "1"], cwd=path)
    # Parse 'commit <sha>'
    sha = res.stdout.splitlines()[0].split()[1]
    
    res = repo_factory.run(["show", sha], cwd=path)
    assert "initial" in res.stdout
    assert "f.txt" in res.stdout

def test_diff_stat(repo_factory):
    """Test diff summary and stat output."""
    path = repo_factory.create()
    (path / "f1.txt").write_text("data 1")
    (path / "f2.txt").write_text("data 2")
    repo_factory.run(["add", "."], cwd=path)
    
    res = repo_factory.run(["diff", "--staged", "--stat"], cwd=path)
    assert "f1.txt" in res.stdout
    assert "f2.txt" in res.stdout
    assert "2 files changed" in res.stdout or "2 files" in res.stdout
