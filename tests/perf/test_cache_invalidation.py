import subprocess
import pytest
from pathlib import Path
from deep.storage.cache import CacheManager

def run_deep(*args, cwd=None):
    import sys
    cmd = [sys.executable, "-m", "deep.cli.main"] + list(args)
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)

def test_transaction_invalidates_cache(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    run_deep("init", cwd=repo)
    
    # 1. Create a dummy cache file
    # Note: CacheManager expects the .deep directory or repo root
    # Our CacheManager fix handles both but TransactionManager passes repo/.deep
    cm = CacheManager(repo / ".deep")
    cm.update_commit_graph([{"sha": "old"}])
    cache_file = repo / ".deep" / "cache" / "commit_graph.json"
    assert cache_file.exists()
    
    # 2. Perform a mutation (commit)
    (repo / "file.txt").write_text("hello", encoding="utf-8")
    run_deep("add", ".", cwd=repo)
    res = run_deep("commit", "-m", "mutation", cwd=repo)
    
    if res.returncode != 0:
        print(res.stdout)
        print(res.stderr)
        
    assert res.returncode == 0
    
    # 3. Verify cache was invalidated (deleted)
    assert not cache_file.exists(), "Cache file should have been deleted by TransactionManager.commit()"

def test_failed_transaction_does_not_invalidate_cache(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    run_deep("init", cwd=repo)
    
    cm = CacheManager(repo / ".deep")
    cm.update_commit_graph([{"sha": "old"}])
    cache_file = repo / ".deep" / "cache" / "commit_graph.json"
    
    # Perform a mutation that will fail (e.g. commit without changes if not forced, or just an invalid command)
    # Actually, a rollback should NOT invalidate the cache? 
    # Usually we invalidate only on SUCCESSFUL commit.
    
    # Let's try to trigger a rollback. e.g. p2p sync to dead port
    res = run_deep("p2p", "sync", "--peer", "localhost:1", cwd=repo)
    assert res.returncode != 0
    
    # Cache should STILL BE THERE (no point in invalidating if no change was made)
    assert cache_file.exists()
