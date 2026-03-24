import pytest
from pathlib import Path

def test_merge_conflict_markers_and_abort(repo_factory):
    """Verify conflict markers and merge abort."""
    path = repo_factory.create()
    f = path / "conf.txt"
    f.write_text("line 1\nline 2")
    repo_factory.run(["add", "conf.txt"], cwd=path)
    repo_factory.run(["commit", "-m", "base"], cwd=path)
    
    # Branch 1
    repo_factory.run(["checkout", "-b", "b1"], cwd=path)
    f.write_text("line 1 edit b1\nline 2")
    repo_factory.run(["add", "conf.txt"], cwd=path)
    repo_factory.run(["commit", "-m", "b1 edit"], cwd=path)
    
    # Main edit
    repo_factory.run(["checkout", "main"], cwd=path)
    f.write_text("line 1 edit main\nline 2")
    repo_factory.run(["add", "conf.txt"], cwd=path)
    repo_factory.run(["commit", "-m", "main edit"], cwd=path)
    
    # Merge b1 into main
    res = repo_factory.run(["merge", "b1"], cwd=path)
    # Expect conflict
    assert res.returncode != 0
    assert "CONFLICT" in res.stdout or "<<<<" in f.read_text()
    
    # Merge abort
    res = repo_factory.run(["merge", "--abort"], cwd=path)
    assert res.returncode == 0
    assert f.read_text() == "line 1 edit main\nline 2"

def test_merge_resolve_flow(repo_factory):
    """Verify full merge resolution flow."""
    path = repo_factory.create()
    f = path / "conf.txt"
    f.write_text("base")
    repo_factory.run(["add", "conf.txt"], cwd=path)
    repo_factory.run(["commit", "-m", "base"], cwd=path)
    
    repo_factory.run(["branch", "feat"], cwd=path)
    f.write_text("main edit")
    repo_factory.run(["add", "conf.txt"], cwd=path)
    repo_factory.run(["commit", "-m", "main edit"], cwd=path)
    
    repo_factory.run(["checkout", "feat"], cwd=path)
    f.write_text("feat edit")
    repo_factory.run(["add", "conf.txt"], cwd=path)
    repo_factory.run(["commit", "-m", "feat edit"], cwd=path)
    
    repo_factory.run(["checkout", "main"], cwd=path)
    repo_factory.run(["merge", "feat"], cwd=path)
    
    # Resolve
    f.write_text("resolved content")
    repo_factory.run(["add", "conf.txt"], cwd=path)
    # Explicit deep merge --continue if available or just commit
    res = repo_factory.run(["commit", "-m", "resolved merge"], cwd=path)
    assert res.returncode == 0
    
    res = repo_factory.run(["status"], cwd=path)
    assert "nothing to commit" in res.stdout.lower()
