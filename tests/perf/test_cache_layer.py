import subprocess
import os
import time
import json
import pytest
from pathlib import Path
from deep.storage.cache import CacheManager
from deep.storage.objects import generate_object_index, read_object, Commit
from deep.core.snapshot import RepositorySnapshot

def run_deep(*args, cwd=None):
    import sys
    cmd = [sys.executable, "-m", "deep.cli.main"] + list(args)
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)

def test_commit_graph_cache(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    run_deep("init", cwd=repo)
    
    # Create some history
    for i in range(5):
        (repo / f"file_{i}.txt").write_text(f"content {i}", encoding="utf-8")
        run_deep("add", ".", cwd=repo)
        run_deep("commit", "-m", f"commit {i}", cwd=repo)
    
    cm = CacheManager(repo)
    # Simulate computing graph
    graph = [{"sha": "abc", "parents": []}]
    cm.update_commit_graph(graph)
    
    loaded = cm.get_commit_graph()
    assert loaded == graph
    assert (repo / ".deep" / "cache" / "commit_graph.json").exists()

def test_diff_cache(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    run_deep("init", cwd=repo)
    
    cm = CacheManager(repo)
    sha1, sha2 = "1111", "2222"
    diff_text = "some diff content"
    
    cm.set_diff(sha1, sha2, diff_text)
    assert cm.get_diff(sha1, sha2) == diff_text
    assert (repo / ".deep" / "cache" / "diffs" / f"{sha1}_{sha2}.diff").exists()

def test_object_lookup_speed(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    run_deep("init", cwd=repo)
    
    # Create objects and pack them
    (repo / "perf.txt").write_text("performance test", encoding="utf-8")
    run_deep("add", "perf.txt", cwd=repo)
    run_deep("commit", "-m", "perf", cwd=repo)
    
    # Force a repack (assuming we have a repack command or we can just use the storage layer)
    # For this test, we just want to verify generate_object_index works and read_object uses it.
    index = generate_object_index(repo)
    assert len(index) > 0
    assert any(loc == "loose" for loc in index.values())
    
    # Verify read_object still works with index present
    from deep.core.refs import resolve_head
    head_sha = resolve_head(repo / ".deep")
    obj = read_object(repo / ".deep" / "objects", head_sha)
    assert isinstance(obj, Commit)

def test_snapshot_consistency(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    run_deep("init", cwd=repo)
    
    (repo / "f1.txt").write_text("v1", encoding="utf-8")
    run_deep("add", ".", cwd=repo)
    run_deep("commit", "-m", "first", cwd=repo)
    
    from deep.core.refs import resolve_head
    first_sha = resolve_head(repo / ".deep")
    
    # Create snapshot at first_sha
    snap = RepositorySnapshot(repo, first_sha)
    
    # Create another commit
    (repo / "f1.txt").write_text("v2", encoding="utf-8")
    run_deep("add", ".", cwd=repo)
    run_deep("commit", "-m", "second", cwd=repo)
    
    # Snapshot should still point to first_sha
    assert snap.snapshot_sha == first_sha
    summary = snap.get_status_summary()
    assert summary["snapshot_sha"] == first_sha
    assert "first" in summary["head_message"]
