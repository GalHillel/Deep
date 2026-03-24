import pytest

def test_auth_and_user(repo_factory):
    """Test auth and user commands by registering and capturing tokens."""
    path = repo_factory.create("auth_test")
    token = repo_factory.login(cwd=path)
    assert token is not None
    
    # Verify user show
    res = repo_factory.run(["user", "show"], cwd=path)
    assert "tester" in res.stdout.lower()

def test_platform_comprehensive(repo_factory):
    """Test integrated platform features: issues, PRs, and pipelines."""
    path = repo_factory.create()
    repo_factory.login(cwd=path)
    
    # 1. Issues
    repo_factory.run(["issue", "create", "--title", "Bug A", "--type", "bug"], cwd=path)
    res = repo_factory.run(["issue", "list"], cwd=path)
    assert "Bug A" in res.stdout
    
    # 2. PR Flow
    (path / "f.txt").write_text("base")
    repo_factory.run(["add", "f.txt"], cwd=path)
    repo_factory.run(["commit", "-m", "base"], cwd=path)
    repo_factory.run(["checkout", "-b", "feat"], cwd=path)
    (path / "f.txt").write_text("mod")
    repo_factory.run(["add", "f.txt"], cwd=path)
    repo_factory.run(["commit", "-m", "mod"], cwd=path)
    
    repo_factory.run(["pr", "create", "--title", "Mod PR"], cwd=path)
    repo_factory.run(["pr", "review", "1", "--state", "approved"], cwd=path)
    res = repo_factory.run(["pr", "merge", "1"], cwd=path)
    assert res.returncode == 0
    
    # 3. Pipelines
    repo_factory.run(["pipeline", "run"], cwd=path)
    res = repo_factory.run(["pipeline", "status"], cwd=path)
    assert res.returncode == 0

def test_pr_and_issue_repetition(repo_factory):
    """Test pr and issue commands 10 times to ensure stability."""
    path = repo_factory.create("stability_test")
    repo_factory.login(cwd=path)
    for i in range(1, 11):
        # Issue
        res = repo_factory.run(["issue", "create", "-t", f"Issue {i}"], cwd=path)
        assert res.returncode == 0
        
        # PR (requires branches)
        repo_factory.run(["checkout", "-b", f"branch_{i}"], cwd=path)
        (path / f"file_{i}.txt").write_text(f"content {i}")
        repo_factory.run(["add", f"file_{i}.txt"], cwd=path)
        repo_factory.run(["commit", "-m", f"commit {i}"], cwd=path)
        res = repo_factory.run(["pr", "create", "-t", f"PR {i}"], cwd=path)
        assert res.returncode == 0
        repo_factory.run(["checkout", "main"], cwd=path)
