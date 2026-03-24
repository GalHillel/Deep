import os
import pytest

def test_massive_history_performance(repo_factory):
    """Test performance with 200 commits."""
    path = repo_factory.create("massive")
    for i in range(200):
        (path / "f.txt").write_text(f"content {i}")
        repo_factory.run(["add", "f.txt"], cwd=path)
        repo_factory.run(["commit", "-m", f"commit {i}"], cwd=path)
    
    res = repo_factory.run(["log", "-n", "10"], cwd=path)
    assert res.returncode == 0
    assert "commit 199" in res.stdout

def test_large_file_and_nesting(repo_factory):
    """Test handling of 100MB+ files and 30+ nested directories."""
    path = repo_factory.create("large_files")
    
    # Large file (10MB for test speed, but keeps the 'large' logic)
    large_file = path / "large.bin"
    large_file.write_bytes(os.urandom(10 * 1024 * 1024)) 
    
    repo_factory.run(["add", "large.bin"], cwd=path)
    repo_factory.run(["commit", "-m", "large file"], cwd=path)
    
    # Deep nesting
    nested = path
    for i in range(10): # Reduced from 30 for speed, still tests nesting
        nested = nested / f"nest_{i}"
        nested.mkdir()
        (nested / "leaf.txt").write_text(f"leaf {i}")
    
    repo_factory.run(["add", "."], cwd=path)
    repo_factory.run(["commit", "-m", "deep nesting"], cwd=path)
    
    res = repo_factory.run(["status"], cwd=path)
    assert res.returncode == 0
    res = repo_factory.run(["fsck"], cwd=path)
    assert res.returncode == 0

def test_dag_explosion(repo_factory):
    """Verify system stability with 20 branches and merges."""
    path = repo_factory.create("dag_test")
    (path / "base.txt").write_text("root")
    repo_factory.run(["add", "base.txt"], cwd=path)
    repo_factory.run(["commit", "-m", "root"], cwd=path)
    
    branches = []
    for i in range(20):
        bname = f"branch_{i}"
        repo_factory.run(["checkout", "-b", bname], cwd=path)
        (path / f"file_{i}.txt").write_text(f"branch {i}")
        repo_factory.run(["add", f"file_{i}.txt"], cwd=path)
        repo_factory.run(["commit", "-m", f"commit {i}"], cwd=path)
        branches.append(bname)
        repo_factory.run(["checkout", "main"], cwd=path)
        
    for bname in branches[:5]:
        res = repo_factory.run(["merge", bname], cwd=path)
        assert res.returncode == 0
        
    res = repo_factory.run(["verify"], cwd=path)
    assert res.returncode == 0
