import pytest
from pathlib import Path

def test_rebase_conflict_and_abort(repo_factory):
    """Verify rebase conflict and abort."""
    path = repo_factory.create()
    f = path / "f.txt"
    f.write_text("base")
    repo_factory.run(["add", "f.txt"], cwd=path)
    repo_factory.run(["commit", "-m", "base"], cwd=path)
    
    # Topic
    repo_factory.run(["checkout", "-b", "topic"], cwd=path)
    f.write_text("topic edit")
    repo_factory.run(["add", "f.txt"], cwd=path)
    repo_factory.run(["commit", "-m", "topic edit"], cwd=path)
    
    # Main edit
    repo_factory.run(["checkout", "main"], cwd=path)
    f.write_text("main edit")
    repo_factory.run(["add", "f.txt"], cwd=path)
    repo_factory.run(["commit", "-m", "main edit"], cwd=path)
    
    # Rebase topic onto main
    repo_factory.run(["checkout", "topic"], cwd=path)
    res = repo_factory.run(["rebase", "main"], cwd=path)
    assert res.returncode != 0
    
    # Abort
    repo_factory.run(["rebase", "--abort"], cwd=path)
    assert f.read_text() == "topic edit"
    res = repo_factory.run(["status"], cwd=path)
    assert "rebase" not in res.stdout.lower()

def test_rebase_continue_flow(repo_factory):
    """Verify rebase --continue after resolution."""
    path = repo_factory.create()
    f = path / "f.txt"
    f.write_text("base")
    repo_factory.run(["add", "f.txt"], cwd=path)
    repo_factory.run(["commit", "-m", "base"], cwd=path)
    
    repo_factory.run(["branch", "feat"], cwd=path)
    f.write_text("main edit")
    repo_factory.run(["add", "f.txt"], cwd=path)
    repo_factory.run(["commit", "-m", "main edit"], cwd=path)
    
    repo_factory.run(["checkout", "feat"], cwd=path)
    f.write_text("feat edit")
    repo_factory.run(["add", "f.txt"], cwd=path)
    repo_factory.run(["commit", "-m", "feat edit"], cwd=path)
    
    repo_factory.run(["rebase", "main"], cwd=path)
    
    # Resolve
    f.write_text("resolved")
    repo_factory.run(["add", "f.txt"], cwd=path)
    
    # Continue
    res = repo_factory.run(["rebase", "--continue"], cwd=path)
    # Some deep rebase might need EDITOR or just --no-edit
    if res.returncode != 0 and "EDITOR" in res.stderr:
         res = repo_factory.run(["rebase", "--continue"], cwd=path, env={**repo_factory.env, "EDITOR": "true"})
    
    assert res.returncode == 0
    assert "base" in repo_factory.run(["log"], cwd=path).stdout
