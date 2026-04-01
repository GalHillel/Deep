import subprocess
import os
import shutil
import pytest
from pathlib import Path

@pytest.fixture
def clean_repo(tmp_path):
    """Set up a clean Deep repository with some history."""
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    subprocess.run(["deep", "init"], cwd=str(repo_path), check=True)
    
    # Commit 1
    (repo_path / "f1.txt").write_text("v1")
    subprocess.run(["deep", "add", "."], cwd=str(repo_path), check=True)
    subprocess.run(["deep", "commit", "-m", "commit 1"], cwd=str(repo_path), check=True)
    
    # Commit 2
    (repo_path / "f2.txt").write_text("v2")
    subprocess.run(["deep", "add", "."], cwd=str(repo_path), check=True)
    subprocess.run(["deep", "commit", "-m", "commit 2"], cwd=str(repo_path), check=True)
    
    return repo_path

def test_reset_soft(clean_repo):
    """Verify --soft reset: HEAD moves, index and workdir stay."""
    # current head is commit 2
    subprocess.run(["deep", "reset", "--soft", "HEAD~1"], cwd=str(clean_repo), check=True)
    
    # HEAD should be commit 1
    from deep.core.refs import resolve_head
    from deep.core.constants import DEEP_DIR
    head_sha = resolve_head(clean_repo / DEEP_DIR)
    
    # Verify index still has f2.txt
    from deep.storage.index import read_index
    index = read_index(clean_repo / DEEP_DIR)
    assert "f2.txt" in index.entries
    
    # Verify workdir still has f2.txt
    assert (clean_repo / "f2.txt").exists()

def test_reset_hard(clean_repo):
    """Verify --hard reset: HEAD, index, and workdir match target."""
    subprocess.run(["deep", "reset", "--hard", "HEAD~1"], cwd=str(clean_repo), check=True)
    
    # Verify f2.txt is gone from workdir
    assert not (clean_repo / "f2.txt").exists()
    
    # Verify index does not have f2.txt
    from deep.storage.index import read_index
    from deep.core.constants import DEEP_DIR
    index = read_index(clean_repo / DEEP_DIR)
    assert "f2.txt" not in index.entries

def test_reset_mixed_default(clean_repo):
    """Verify mixed reset (default): HEAD moves, index moves, workdir stays."""
    subprocess.run(["deep", "reset", "HEAD~1"], cwd=str(clean_repo), check=True)
    
    # Verify f2.txt remains on disk
    assert (clean_repo / "f2.txt").exists()
    
    # Verify index does NOT have f2.txt (it was reset to commit 1)
    from deep.storage.index import read_index
    from deep.core.constants import DEEP_DIR
    index = read_index(clean_repo / DEEP_DIR)
    assert "f2.txt" not in index.entries

def test_reset_mutually_exclusive(clean_repo):
    """Verify that using both --hard and --soft fails."""
    res = subprocess.run(["deep", "reset", "--hard", "--soft", "HEAD"], cwd=str(clean_repo), capture_output=True, text=True)
    assert res.returncode != 0
    assert "not allowed with" in res.stderr or "mutually exclusive" in res.stderr
