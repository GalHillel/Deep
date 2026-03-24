import pytest

def test_invalid_args_and_missing_files(repo_factory):
    path = repo_factory.create()
    
    # Invalid command
    res = repo_factory.run(["nonexistent-command"], cwd=path)
    assert res.returncode != 0
    
    # Invalid arg for valid command
    res = repo_factory.run(["add", "--invalid-flag"], cwd=path)
    assert res.returncode != 0

    # Add missing file
    res = repo_factory.run(["add", "missing.txt"], cwd=path)
    assert res.returncode != 0
    assert "error" in res.stderr.lower() or "not found" in res.stderr.lower()
    
    # Remove missing file
    res = repo_factory.run(["rm", "missing.txt"], cwd=path)
    assert res.returncode != 0

def test_rollback_after_failure(repo_factory):
    """Test rollback atomicity."""
    path = repo_factory.create()
    (path / "f.txt").write_text("v1")
    repo_factory.run(["add", "f.txt"], cwd=path)
    repo_factory.run(["commit", "-m", "v1"], cwd=path)
    
    # Rollback to HEAD
    res = repo_factory.run(["rollback"], cwd=path)
    assert res.returncode == 0

def test_rollback_on_failed_commit(repo_factory):
    """Verify that a failed commit doesn't leave the repo in a broken state."""
    path = repo_factory.create()
    # Empty commit fail
    res = repo_factory.run(["commit", "-m", "empty"], cwd=path)
    assert res.returncode != 0
    
    # Verify status is still clean
    res = repo_factory.run(["status"], cwd=path)
    assert "clean" in res.stdout.lower() or "nothing to commit" in res.stdout.lower()

def test_path_chaos(repo_factory):
    """Verify commands work with complex paths (spaces, Unicode)."""
    path = repo_factory("chaos_test")
    
    complex_file = "file with space 🚀.txt"
    (path / complex_file).write_text("chaos")
    
    repo_factory.run(["add", complex_file], cwd=path)
    repo_factory.run(["commit", "-m", "chaos commit"], cwd=path)
    
    res = repo_factory.run(["log"], cwd=path)
    assert "chaos commit" in res.stdout
    assert complex_file in repo_factory.run(["ls-tree", "HEAD"], cwd=path).stdout
