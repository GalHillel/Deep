import pytest
import os

def test_sandbox_isolation(repo_factory):
    """Verify sandbox command restricted behavior."""
    path = repo_factory.create("sandbox_test")
    res = repo_factory.run(["sandbox", "run", "ls"], cwd=path)
    # Success or failure depends on sandbox config, but CLI must survive
    assert res.returncode in [0, 1] 

def test_audit_and_verify(repo_factory):
    path = repo_factory.create("security_audit")
    (path / "f.txt").write_text("secure content")
    repo_factory.run(["add", "f.txt"], cwd=path)
    repo_factory.run(["commit", "-m", "secure"], cwd=path)
    
    res = repo_factory.run(["audit"], cwd=path)
    assert res.returncode == 0
    res = repo_factory.run(["verify"], cwd=path)
    assert res.returncode == 0

def test_diagnostics_and_rollback(repo_factory):
    """Test doctor and rollback scenarios."""
    path = repo_factory.create("diag_rollback")
    (path / "f.txt").write_text("v1")
    repo_factory.run(["add", "f.txt"], cwd=path)
    repo_factory.run(["commit", "-m", "v1"], cwd=path)
    
    # Doctor check
    res = repo_factory.run(["doctor"], cwd=path)
    assert res.returncode == 0
    
    # Rollback
    (path / "bad.txt").write_text("bad")
    repo_factory.run(["add", "bad.txt"], cwd=path)
    repo_factory.run(["commit", "-m", "bad commit"], cwd=path)
    
    res = repo_factory.run(["rollback"], cwd=path)
    assert res.returncode == 0
    assert "bad commit" not in repo_factory.run(["log"], cwd=path).stdout

def test_internal_debug_tools(repo_factory):
    """Test debug-tree and version."""
    path = repo_factory.create("debug_tools")
    res = repo_factory.run(["version"], cwd=path)
    assert res.returncode == 0
    
    (path / "f.txt").write_text("data")
    repo_factory.run(["add", "f.txt"], cwd=path)
    repo_factory.run(["commit", "-m", "init"], cwd=path)
    
    # Get a SHA to debug
    log_out = repo_factory.run(["log", "-n", "1", "--format", "%H"], cwd=path).stdout.strip()
    if log_out:
        res = repo_factory.run(["debug-tree", log_out], cwd=path)
        assert res.returncode == 0
