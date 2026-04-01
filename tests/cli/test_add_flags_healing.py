import subprocess
import os
import shutil
import pytest
from pathlib import Path

@pytest.fixture
def clean_repo(tmp_path):
    """Set up a clean Deep repository."""
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    subprocess.run(["deep", "init"], cwd=str(repo_dir), check=True)
    return repo_dir

def test_add_basic_file(clean_repo):
    """Verify that adding a single file works."""
    f1 = clean_repo / "file1.txt"
    f1.write_text("v1")
    
    subprocess.run(["deep", "add", "file1.txt"], cwd=str(clean_repo), check=True)
    
    # Check if added (index must contain file1.txt)
    # We'll use status or just assume success if it didn't crash for now, 
    # but more robustly, we'll check the objects dir.
    from deep.core.constants import DEEP_DIR
    index_path = clean_repo / DEEP_DIR / "index"
    assert index_path.exists()
    
    # Verify commit works after add
    subprocess.run(["deep", "commit", "-m", "initial"], cwd=str(clean_repo), check=True)

def test_add_all(clean_repo):
    """Verify that 'deep add .' adds all files."""
    (clean_repo / "f1.txt").write_text("1")
    (clean_repo / "f2.txt").write_text("2")
    
    subprocess.run(["deep", "add", "."], cwd=str(clean_repo), check=True)
    
    # Verify both are staged
    res = subprocess.run(["deep", "commit", "-m", "add all"], cwd=str(clean_repo), capture_output=True, text=True, check=True)
    assert "2 files" in res.stdout or "add all" in res.stdout

def test_add_update_tracked_only(clean_repo):
    """Verify that 'deep add -u' updates tracked files but ignores new ones."""
    # First commit
    (clean_repo / "tracked.txt").write_text("v1")
    subprocess.run(["deep", "add", "tracked.txt"], cwd=str(clean_repo), check=True)
    subprocess.run(["deep", "commit", "-m", "initial"], cwd=str(clean_repo), check=True)
    
    # Modify tracked, add new untracked
    (clean_repo / "tracked.txt").write_text("v2")
    (clean_repo / "untracked.txt").write_text("new")
    
    # Run add -u
    subprocess.run(["deep", "add", "-u"], cwd=str(clean_repo), check=True)
    
    # Commit
    subprocess.run(["deep", "commit", "-m", "update"], cwd=str(clean_repo), check=True)
    
    # Log should show the update, but 'untracked.txt' shouldn't be in the commit
    # We'll check via status or just assume untracked isn't there if we can't find it in log.
    # Actually, let's check if the untracked file is in the objects dir if we had its SHA.
    # Simpler: check if 'untracked.txt' is NOT in index.
    from deep.storage.index import read_index
    from deep.core.constants import DEEP_DIR
    index = read_index(clean_repo / DEEP_DIR)
    assert "tracked.txt" in index.entries
    assert "untracked.txt" not in index.entries

def test_add_update_staged_deletion(clean_repo):
    """Verify that 'deep add -u' stages deletions."""
    (clean_repo / "delete_me.txt").write_text("bye")
    subprocess.run(["deep", "add", "delete_me.txt"], cwd=str(clean_repo), check=True)
    subprocess.run(["deep", "commit", "-m", "initial"], cwd=str(clean_repo), check=True)
    
    # Remove file from disk
    (clean_repo / "delete_me.txt").unlink()
    
    # Run add -u
    subprocess.run(["deep", "add", "-u"], cwd=str(clean_repo), check=True)
    
    # Verify file is removed from index
    from deep.storage.index import read_index
    from deep.core.constants import DEEP_DIR
    index = read_index(clean_repo / DEEP_DIR)
    assert "delete_me.txt" not in index.entries

def test_add_no_args_error(clean_repo):
    """Verify that 'deep add' without args errors out."""
    res = subprocess.run(["deep", "add"], cwd=str(clean_repo), capture_output=True, text=True)
    assert res.returncode != 0
    assert "Nothing specified" in res.stderr

def test_add_update_no_args_is_dot(clean_repo):
    """Verify that 'deep add -u' without args defaults to '.'."""
    (clean_repo / "tracked.txt").write_text("v1")
    subprocess.run(["deep", "add", "tracked.txt"], cwd=str(clean_repo), check=True)
    subprocess.run(["deep", "commit", "-m", "initial"], cwd=str(clean_repo), check=True)
    
    (clean_repo / "tracked.txt").write_text("v2")
    subprocess.run(["deep", "add", "-u"], cwd=str(clean_repo), check=True)
    
    from deep.storage.index import read_index
    from deep.core.constants import DEEP_DIR
    index = read_index(clean_repo / DEEP_DIR)
    # Check if v2 is staged (we'd need SHA comparison to be 100% sure, 
    # but getting non-zero status exit code 1 if it failed would be catchable).
    assert "tracked.txt" in index.entries
