import pytest
import os
from pathlib import Path

@pytest.mark.slow
def test_large_repo_scaling(repo_factory):
    """Test repo with many files and deep structure."""
    path = repo_factory.create()
    
    # 1. Many files
    for i in range(500):
        (path / f"file_{i}.txt").write_text(f"content {i}")
    repo_factory.run(["add", "."], cwd=path)
    repo_factory.run(["commit", "-m", "500 files"], cwd=path)
    
    # 2. Deep directories
    base = path
    for i in range(20):
        base = base / f"nest_{i}"
        base.mkdir()
        (base / "leaf.txt").write_text(f"leaf {i}")
    repo_factory.run(["add", "."], cwd=path)
    repo_factory.run(["commit", "-m", "deep nesting"], cwd=path)
    
    # 3. Large files (10MB for test speed, but can be higher)
    large = path / "large.bin"
    with open(large, "wb") as f:
        f.write(os.urandom(10 * 1024 * 1024))
    repo_factory.run(["add", "large.bin"], cwd=path)
    repo_factory.run(["commit", "-m", "large file"], cwd=path)
    
    res = repo_factory.run(["status"], cwd=path)
    assert res.returncode == 0
    res = repo_factory.run(["fsck"], cwd=path)
    assert res.returncode == 0

@pytest.mark.slow
def test_commit_history_depth(repo_factory):
    """Test repo with hundreds of sequential commits."""
    path = repo_factory.create()
    for i in range(200):
        (path / "log.txt").write_text(f"log {i}")
        repo_factory.run(["add", "log.txt"], cwd=path)
        repo_factory.run(["commit", "-m", f"commit {i}"], cwd=path)
    
    res = repo_factory.run(["log", "-n", "10"], cwd=path)
    assert res.returncode == 0
    assert "commit 199" in res.stdout
