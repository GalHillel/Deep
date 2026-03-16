"""Tests for historical search (Phase 46)."""
from pathlib import Path
import subprocess, sys, os, json
import pytest

from deep.core.repository import DEEP_DIR


@pytest.fixture
def search_repo(tmp_path):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path.cwd() / "src")
    subprocess.run([sys.executable, "-m", "deep.main", "init"], cwd=tmp_path, env=env, check=True)
    
    # Commit 1
    (tmp_path / "a.txt").write_text("hello search world")
    subprocess.run([sys.executable, "-m", "deep.main", "add", "a.txt"], cwd=tmp_path, env=env, check=True)
    subprocess.run([sys.executable, "-m", "deep.main", "commit", "-m", "c1"], cwd=tmp_path, env=env, check=True)
    
    # Commit 2
    (tmp_path / "b.txt").write_text("deep rulez")
    subprocess.run([sys.executable, "-m", "deep.main", "add", "b.txt"], cwd=tmp_path, env=env, check=True)
    subprocess.run([sys.executable, "-m", "deep.main", "commit", "-m", "c2"], cwd=tmp_path, env=env, check=True)
    
    return tmp_path, env


def test_search_history_hits(search_repo):
    repo, env = search_repo
    result = subprocess.run(
        [sys.executable, "-m", "deep.main", "search", "search"],
        cwd=repo, env=env, capture_output=True, text=True, check=True
    )
    assert "a.txt" in result.stdout
    assert "hello search world" in result.stdout


def test_search_history_no_hits(search_repo):
    repo, env = search_repo
    result = subprocess.run(
        [sys.executable, "-m", "deep.main", "search", "nonexistent_pattern_123"],
        cwd=repo, env=env, capture_output=True, text=True, check=True
    )
    assert "No matches found" in result.stdout


def test_semantic_blame(search_repo):
    from deep.core.blame import semantic_blame
    repo, env = search_repo
    dg_dir = repo / DEEP_DIR
    
    # Add a function
    (repo / "code.py").write_text("def my_func():\n    pass")
    subprocess.run([sys.executable, "-m", "deep.main", "add", "code.py"], cwd=repo, env=env, check=True)
    subprocess.run([sys.executable, "-m", "deep.main", "commit", "-m", "add func"], cwd=repo, env=env, check=True)
    
    authors = semantic_blame(dg_dir, "code.py")
    assert "my_func" in authors
