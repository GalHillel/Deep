import pytest
import multiprocessing
import time
import requests
import json
import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from deep.web.dashboard import start_dashboard
from deep.core.repository import init_repo
from deep.commands import add_cmd, commit_cmd

def ns(**kwargs):
    import argparse
    return argparse.Namespace(**kwargs)

@pytest.fixture
def repo_with_server(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)
    
    # Start server in a background process
    proc = multiprocessing.Process(target=start_dashboard, args=(repo, "127.0.0.1", 9091))
    proc.daemon = True
    proc.start()
    
    # Wait for server to be ready
    max_retries = 10
    while max_retries > 0:
        try:
            requests.get("http://127.0.0.1:9091/api/status")
            break
        except:
            time.sleep(0.5)
            max_retries -= 1
            
    yield repo, "http://127.0.0.1:9091"
    
    proc.terminate()
    proc.join()

def test_dashboard_thread_safety(repo_with_server):
    repo, url = repo_with_server
    
    # Add some data
    (repo / "test.py").write_text("print('hello')")
    os.chdir(repo)
    add_cmd.run(ns(files=["test.py"]))
    commit_cmd.run(ns(message="initial", ai=False, allow_empty=True, all=False, amend=False))
    
    def make_request(i):
        # Alternate between different endpoints to stress thread safety
        endpoint = "/api/graph" if i % 2 == 0 else "/api/tree"
        resp = requests.get(f"{url}{endpoint}")
        return resp.status_code

    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(make_request, range(20)))
        
    assert all(r == 200 for r in results)

def test_dashboard_empty_repo(tmp_path):
    # Specialized test for empty repo
    repo = tmp_path / "empty_repo"
    repo.mkdir()
    init_repo(repo)
    
    proc = multiprocessing.Process(target=start_dashboard, args=(repo, "127.0.0.1", 9092))
    proc.daemon = True
    proc.start()
    
    try:
        # Wait for ready
        time.sleep(2)
        resp = requests.get("http://127.0.0.1:9092/api/graph")
        assert resp.status_code == 200
        data = resp.json()
        assert "commits" in data or "data" in data # v2 might wrap in data
        # Check if it's empty
        res_data = data.get("data", data)
        assert len(res_data.get("commits", [])) == 0
    finally:
        proc.terminate()

def test_dashboard_v2_fallback(repo_with_server, monkeypatch):
    repo, url = repo_with_server
    
    # We can't monkeypatch the remote process easily, but we can corrupt the cache
    cache_file = repo / ".deep" / "cache" / "commit_graph.json"
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text("invalid json { content")
    
    # Request graph - should trigger V2 failure and V1 fallback
    resp = requests.get(f"{url}/api/graph")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    # If it fell back to V1, it might not have the "source": "cache" field but it should have commits
    assert "commits" in data["data"]

def test_atomic_cache_write(tmp_path):
    from deep.storage.cache import CacheManager
    from deep.storage.atomic import AtomicWriter
    
    repo = tmp_path / "atomic_repo"
    repo.mkdir()
    init_repo(repo)
    cm = CacheManager(repo / ".deep")
    
    def concurrent_write(i):
        # Large data to increase write window
        data = [{"sha": f"sha{j}", "parents": []} for j in range(1000)]
        cm.update_commit_graph(data)
        return True

    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(concurrent_write, range(10)))
        
    assert all(results)
    # Final check: JSON is valid
    graph = cm.get_commit_graph()
    assert len(graph) == 1000
