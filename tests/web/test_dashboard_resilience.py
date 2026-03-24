import pytest
import os
import json
from pathlib import Path
from deep.web.services import DashboardService
from deep.core.repository import init_repo
from deep.commands.add_cmd import run as run_add
from deep.commands.commit_cmd import run as run_commit
import argparse

def ns(**kwargs):
    return argparse.Namespace(**kwargs)

@pytest.fixture
def repo(tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    os.chdir(repo_dir)
    init_repo(repo_dir)
    return repo_dir

def test_graph_v2_default(repo):
    dg_dir = repo / ".deep"
    service = DashboardService(dg_dir, repo)
    
    # 1. Test empty repo (no cache)
    res = service.get_graph_v2()
    assert res["success"] is True
    data = res["data"]
    assert data["v"] == 2
    assert data["source"] == "v1_fallback"
    assert len(data["commits"]) == 0

    # 2. Add a commit
    (repo / "file.txt").write_text("hello")
    run_add(ns(files=["file.txt"]))
    run_commit(ns(message="initial commit", ai=False, allow_empty=True, all=False, amend=False))
    
    # Manually populate cache for testing V2 path
    from deep.storage.cache import CacheManager
    cm = CacheManager(dg_dir)
    cm.update_commit_graph([{"sha": "fake_sha", "message": "hello", "parents": []}])
    
    res = service.get_graph_v2()
    assert res["success"] is True
    data = res["data"]
    assert data["v"] == 2
    assert data["source"] == "cache"
    assert len(data["commits"]) == 1

def test_commit_details_v2_semantics(repo):
    dg_dir = repo / ".deep"
    service = DashboardService(dg_dir, repo)
    
    # Add a semantic commit
    (repo / "logic.py").write_text("def test():\n    try:\n        pass\n    except: pass\n")
    run_add(ns(files=["logic.py"]))
    run_commit(ns(message="feat: add logic with error handling", ai=False, allow_empty=True, all=False, amend=False))
    
    from deep.core.refs import resolve_head
    sha = resolve_head(dg_dir)
    
    res = service.get_commit_details_v2(sha)
    assert res["success"] is True
    data = res["data"]
    assert data["v"] == 2
    assert "intent" in data
    assert "risk" in data
    assert "semver" in data
    assert "add error handling" in data["intent"]
    assert "feat" in data["intent"]

def test_branches_v2(repo):
    dg_dir = repo / ".deep"
    service = DashboardService(dg_dir, repo)
    
    # First commit creates main
    (repo / "init.txt").write_text("orig")
    run_add(ns(files=["init.txt"]))
    run_commit(ns(message="init", ai=False, allow_empty=True, all=False, amend=False))
    
    res = service.get_branches_v2()
    assert res["success"] is True
    assert "main" in res["data"]
