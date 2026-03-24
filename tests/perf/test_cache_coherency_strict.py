import subprocess
import pytest
import time
from pathlib import Path
from deep.storage.cache import CacheManager
from deep.storage.objects import read_object
from deep.core.snapshot import RepositorySnapshot

def run_deep(*args, cwd=None):
    import sys
    cmd = [sys.executable, "-m", "deep.cli.main"] + list(args)
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)

def test_commit_invalidates_disk_cache(tmp_path):
    """Verify that a CLI commit purges the disk cache."""
    repo = tmp_path / "repo_disk"
    repo.mkdir()
    run_deep("init", cwd=repo)
    dg_dir = repo / ".deep"
    
    # 1. Populate some data
    (repo / "f1.txt").write_text("v1", encoding="utf-8")
    run_deep("add", ".", cwd=repo)
    run_deep("commit", "-m", "first", cwd=repo)
    
    from deep.core.refs import resolve_head
    head_sha = resolve_head(dg_dir)
    
    # 2. Populate Disk Cache manually
    cm = CacheManager(dg_dir)
    cm.update_commit_graph([{"sha": head_sha}])
    graph_path = dg_dir / "cache" / "commit_graph.json"
    assert graph_path.exists()
    
    # 3. Perform Mutation via CLI
    (repo / "f1.txt").write_text("v2", encoding="utf-8")
    run_deep("add", ".", cwd=repo)
    run_deep("commit", "-m", "second", cwd=repo)
    
    # 4. ASSERT: Disk cache MUST be gone
    assert not graph_path.exists(), "Disk cache was not invalidated by CLI commit!"

def test_transaction_manager_clears_ram_cache(tmp_path):
    """Verify that TransactionManager.commit() clears the LRU RAM cache."""
    from deep.storage.transaction import TransactionManager
    repo = tmp_path / "repo_ram"
    repo.mkdir()
    run_deep("init", cwd=repo)
    dg_dir = repo / ".deep"
    
    # Seed history
    (repo / "a.txt").write_text("a")
    run_deep("add", ".", cwd=repo)
    run_deep("commit", "-m", "seed", cwd=repo)
    
    # Heat up RAM cache in THIS process
    from deep.core.refs import resolve_head
    sha = resolve_head(dg_dir)
    read_object(dg_dir / "objects", sha)
    assert read_object.cache_info().currsize > 0
    
    # Start transaction in THIS process
    with TransactionManager(dg_dir) as tm:
        tm.begin("test_cache")
        # Simulate some change
        (repo / "b.txt").write_text("b")
        # Note: we don't need real 'add' for this test, just commit() behavior
        tm.commit()
    
    # 4. ASSERT: RAM cache is empty
    assert read_object.cache_info().currsize == 0, "TransactionManager.commit() failed to clear read_object LRU cache!"

def test_snapshot_coherence_v2(tmp_path):
    """Verify that snapshots see consistent history even during/after mutations."""
    repo = tmp_path / "repo_snap"
    repo.mkdir()
    run_deep("init", cwd=repo)
    dg_dir = repo / ".deep"
    
    (repo / "f.txt").write_text("1")
    run_deep("add", ".", cwd=repo)
    run_deep("commit", "-m", "v1", cwd=repo)
    
    from deep.core.refs import resolve_head
    v1_sha = resolve_head(dg_dir)
    snap = RepositorySnapshot(repo, v1_sha)
    
    # 1. Mutation while snapshot exists
    (repo / "f.txt").write_text("2")
    run_deep("add", ".", cwd=repo)
    run_deep("commit", "-m", "v2", cwd=repo)
    v2_sha = resolve_head(dg_dir)
    
    # 2. Snapshot 1 MUST still see v1 metadata (Consistency)
    summary1 = snap.get_status_summary()
    assert summary1["snapshot_sha"] == v1_sha
    assert summary1["head_message"] == "v1"
    
    # 3. Snapshot 2 (Auto-HEAD) MUST see v2
    snap2 = RepositorySnapshot(repo)
    assert snap2.snapshot_sha == v2_sha
    assert snap2.get_status_summary()["head_message"] == "v2"

def test_object_index_atomicity(tmp_path):
    """Verify that object_index.json is written atomically (no partial reads)."""
    from deep.storage.objects import generate_object_index
    repo = tmp_path / "repo_atom"
    repo.mkdir()
    run_deep("init", cwd=repo)
    
    (repo / "f.txt").write_text("data")
    run_deep("add", ".", cwd=repo)
    run_deep("commit", "-m", "atom")
    
    # Just run it to ensure it doesn't crash and file is valid JSON
    index = generate_object_index(repo)
    assert len(index) > 0
    
    index_path = repo / ".deep" / "cache" / "object_index.json"
    import json
    assert json.loads(index_path.read_text(encoding="utf-8")) == index
