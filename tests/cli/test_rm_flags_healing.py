import subprocess
import os
import shutil
import pytest
from pathlib import Path

@pytest.fixture
def clean_repo(tmp_path):
    """Set up a clean Deep repository."""
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    subprocess.run(["deep", "init"], cwd=str(repo_path), check=True)
    return repo_path

def test_rm_basic(clean_repo):
    """Verify that removing a file from index and disk works."""
    f1 = clean_repo / "file1.txt"
    f1.write_text("v1")
    subprocess.run(["deep", "add", "file1.txt"], cwd=str(clean_repo), check=True)
    subprocess.run(["deep", "commit", "-m", "init"], cwd=str(clean_repo), check=True)
    
    # Run rm
    subprocess.run(["deep", "rm", "file1.txt"], cwd=str(clean_repo), check=True)
    
    # Check disk
    assert not f1.exists()
    
    # Check index
    from deep.storage.index import read_index
    from deep.core.constants import DEEP_DIR
    index = read_index(clean_repo / DEEP_DIR)
    assert "file1.txt" not in index.entries

def test_rm_cached(clean_repo):
    """Verify that removing a file with --cached keeps it on disk."""
    f1 = clean_repo / "file1.txt"
    f1.write_text("v1")
    subprocess.run(["deep", "add", "file1.txt"], cwd=str(clean_repo), check=True)
    subprocess.run(["deep", "commit", "-m", "init"], cwd=str(clean_repo), check=True)
    
    # Run rm --cached
    subprocess.run(["deep", "rm", "--cached", "file1.txt"], cwd=str(clean_repo), check=True)
    
    # Check disk (should still exist)
    assert f1.exists()
    
    # Check index (should be gone)
    from deep.storage.index import read_index
    from deep.core.constants import DEEP_DIR
    index = read_index(clean_repo / DEEP_DIR)
    assert "file1.txt" not in index.entries

def test_rm_recursive(clean_repo):
    """Verify that removing a directory recursively works."""
    d1 = clean_repo / "dir1"
    d1.mkdir()
    (d1 / "f1.txt").write_text("1")
    (d1 / "f2.txt").write_text("2")
    subprocess.run(["deep", "add", "."], cwd=str(clean_repo), check=True)
    subprocess.run(["deep", "commit", "-m", "init"], cwd=str(clean_repo), check=True)
    
    # Run rm -r
    subprocess.run(["deep", "rm", "-r", "dir1"], cwd=str(clean_repo), check=True)
    
    # Check disk
    assert not (d1 / "f1.txt").exists()
    assert not (d1 / "f2.txt").exists()
    
    # Check index
    from deep.storage.index import read_index
    from deep.core.constants import DEEP_DIR
    index = read_index(clean_repo / DEEP_DIR)
    assert "dir1/f1.txt" not in index.entries
    assert "dir1/f2.txt" not in index.entries

def test_rm_dir_without_recursive_flag(clean_repo):
    """Verify that removing a directory without -r fails."""
    d1 = clean_repo / "dir1"
    d1.mkdir()
    (d1 / "f1.txt").write_text("1")
    subprocess.run(["deep", "add", "."], cwd=str(clean_repo), check=True)
    
    res = subprocess.run(["deep", "rm", "dir1"], cwd=str(clean_repo), capture_output=True, text=True)
    assert res.returncode != 0
    assert "directory" in res.stderr

def test_rm_untracked_file_error(clean_repo):
    """Verify that removing an untracked file fails."""
    f1 = clean_repo / "untracked.txt"
    f1.write_text("hi")
    
    res = subprocess.run(["deep", "rm", "untracked.txt"], cwd=str(clean_repo), capture_output=True, text=True)
    assert res.returncode != 0
    assert "not tracked" in res.stderr
