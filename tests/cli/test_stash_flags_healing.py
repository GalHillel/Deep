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
    subprocess.run(["deep", "commit", "-m", "init"], cwd=str(repo_path), check=True)
    
    return repo_path

def test_stash_save_message_list(clean_repo):
    """Verify 'deep stash save "msg"' and 'deep stash list'."""
    f1 = clean_repo / "f2.txt"
    f1.write_text("modified")
    subprocess.run(["deep", "add", "f2.txt"], cwd=str(clean_repo), check=True)
    
    # Save stash
    subprocess.run(["deep", "stash", "save", "My Work"], cwd=str(clean_repo), check=True)
    
    # Check disk (should be reset)
    assert not f1.exists()
    
    # Check list
    res = subprocess.run(["deep", "stash", "list"], cwd=str(clean_repo), capture_output=True, text=True, check=True)
    assert "stash@{0}: My Work" in res.stdout

def test_stash_apply(clean_repo):
    """Verify 'deep stash apply' preserves the stash."""
    (clean_repo / "f2.txt").write_text("data")
    subprocess.run(["deep", "add", "f2.txt"], cwd=str(clean_repo), check=True)
    subprocess.run(["deep", "stash", "save", "work"], cwd=str(clean_repo), check=True)
    
    # Apply
    subprocess.run(["deep", "stash", "apply"], cwd=str(clean_repo), check=True)
    
    # Check disk
    assert (clean_repo / "f2.txt").read_text() == "data"
    
    # Check list (still exists)
    res = subprocess.run(["deep", "stash", "list"], cwd=str(clean_repo), capture_output=True, text=True, check=True)
    assert "stash@{0}" in res.stdout

def test_stash_pop(clean_repo):
    """Verify 'deep stash pop' removes the stash."""
    (clean_repo / "f2.txt").write_text("data")
    subprocess.run(["deep", "add", "f2.txt"], cwd=str(clean_repo), check=True)
    subprocess.run(["deep", "stash", "save", "work"], cwd=str(clean_repo), check=True)
    
    # Pop
    subprocess.run(["deep", "stash", "pop"], cwd=str(clean_repo), check=True)
    
    # Check disk
    assert (clean_repo / "f2.txt").read_text() == "data"
    
    # Check list (empty)
    res = subprocess.run(["deep", "stash", "list"], cwd=str(clean_repo), capture_output=True, text=True, check=True)
    assert "stash@{0}" not in res.stdout

def test_stash_clear(clean_repo):
    """Verify 'deep stash clear' empties the stack."""
    (clean_repo / "f1.txt").write_text("v2")
    subprocess.run(["deep", "add", "f1.txt"], cwd=str(clean_repo), check=True)
    subprocess.run(["deep", "stash", "save"], cwd=str(clean_repo), check=True)
    (clean_repo / "f1.txt").write_text("v3")
    subprocess.run(["deep", "add", "f1.txt"], cwd=str(clean_repo), check=True)
    subprocess.run(["deep", "stash", "save"], cwd=str(clean_repo), check=True)
    
    # Check list has 2
    res = subprocess.run(["deep", "stash", "list"], cwd=str(clean_repo), capture_output=True, text=True, check=True)
    assert "stash@{1}" in res.stdout
    
    # Clear
    subprocess.run(["deep", "stash", "clear"], cwd=str(clean_repo), check=True)
    
    # Check list (empty)
    res = subprocess.run(["deep", "stash", "list"], cwd=str(clean_repo), capture_output=True, text=True, check=True)
    assert res.stdout.strip() == ""

def test_stash_drop(clean_repo):
    """Verify 'deep stash drop' removes a specific stash."""
    (clean_repo / "f1.txt").write_text("v2")
    subprocess.run(["deep", "add", "f1.txt"], cwd=str(clean_repo), check=True)
    subprocess.run(["deep", "stash", "save", "stash 0"], cwd=str(clean_repo), check=True)
    (clean_repo / "f1.txt").write_text("v3")
    subprocess.run(["deep", "add", "f1.txt"], cwd=str(clean_repo), check=True)
    subprocess.run(["deep", "stash", "save", "stash 1"], cwd=str(clean_repo), check=True)
    
    # Current list (newest first):
    # stash@{0}: stash 1
    # stash@{1}: stash 0
    
    # Drop stash@{0}
    subprocess.run(["deep", "stash", "drop", "stash@{0}"], cwd=str(clean_repo), check=True)
    
    # Remaining should be stash 0
    res = subprocess.run(["deep", "stash", "list"], cwd=str(clean_repo), capture_output=True, text=True, check=True)
    assert "stash 0" in res.stdout
    assert "stash 1" not in res.stdout
