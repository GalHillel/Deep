import os
import signal
import time
import subprocess
import pytest

def test_crash_during_repack(repo_factory):
    """Simulate a crash during an expensive operation under isolation."""
    path = repo_factory.create()
    for i in range(100):
        (path / f"file_{i}.txt").write_text(f"content {i}" * 100)
        repo_factory.run(["add", f"file_{i}.txt"], cwd=path)
        repo_factory.run(["commit", "-m", f"commit {i}"], cwd=path)
        
    proc = repo_factory.spawn(["repack"], cwd=path)
    time.sleep(0.2)
    proc.kill() # Simulate hard crash
    
    # Verify repo still works
    res = repo_factory.run(["fsck"], cwd=path)
    if res.returncode != 0 and "lock" in res.stderr.lower():
        repo_factory.run(["maintenance", "--force"], cwd=path)
        res = repo_factory.run(["fsck"], cwd=path)
    assert res.returncode == 0

def test_interrupted_commit(repo_factory):
    """Check transaction atomicity with interrupted commit."""
    path = repo_factory.create()
    (path / "staged.txt").write_text("new data")
    repo_factory.run(["add", "staged.txt"], cwd=path)
    
    proc = repo_factory.spawn(["commit", "-m", "interrupted"], cwd=path)
    time.sleep(0.01)
    proc.kill()
    
    # Repository integrity check
    res = repo_factory.run(["fsck"], cwd=path)
    assert res.returncode == 0
    res = repo_factory.run(["status"], cwd=path)
    assert res.returncode == 0

