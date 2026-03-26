"""
tests.core.test_status
~~~~~~~~~~~~~~~~~~~~~~
Core engine tests for status and Git coexistence.
"""

import os
import shutil
import subprocess
from pathlib import Path
import pytest
from deep.core.status import compute_status
from deep.core.repository import init_repo
from deep.storage.index import add_to_index
from deep.core.state import validate_repo_state
from deep.core.git_compat import is_git_managed

@pytest.fixture
def repo_with_git(tmp_path):
    """Create a Deep repo inside a Git repo."""
    repo_dir = tmp_path / "mixed_repo"
    repo_dir.mkdir()
    
    # Init Git
    subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
    (repo_dir / "git_only.txt").write_text("git content")
    subprocess.run(["git", "add", "git_only.txt"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "git commit"], cwd=repo_dir, check=True, capture_output=True)
    
    # Init Deep
    init_repo(repo_dir)
    return repo_dir

def test_status_ignores_git_internal(repo_with_git):
    """Verify that .git directory is ignored by Deep status walk."""
    status = compute_status(repo_with_git)
    # .git should not be in untracked
    assert not any(p.startswith(".git") for p in status.untracked)
    # git_only.txt should be untracked for Deep (since it's not in Deep index)
    assert "git_only.txt" in status.untracked

def test_is_git_managed_utility(repo_with_git):
    """Test the is_git_managed helper."""
    assert is_git_managed(repo_with_git, ".git/config")
    assert is_git_managed(repo_with_git, "git_only.txt") # Tracked by Git
    assert not is_git_managed(repo_with_git, "deep_only.txt")

def test_validate_repo_state_with_git_files(repo_with_git):
    """Verify validate_repo_state doesn't fail due to Git-managed files."""
    # If we modify a Git-managed file, it shouldn't trigger the "dirty" error in Deep.
    (repo_with_git / "git_only.txt").write_text("changed by user")
    
    # validate_repo_state should PASS because git_only.txt is ignored.
    validate_repo_state(repo_with_git)

def test_binary_output_truncation_check(monkeypatch):
    """Verify our objects have truncated repr to avoid log floods."""
    monkeypatch.setenv("DEEP_DEBUG", "0")
    from deep.storage.objects import Blob
    large_data = b"x" * 1000
    blob = Blob(data=large_data)
    r = repr(blob)
    assert "len=1000" in r
    assert len(r) < 200 # Should be truncated
    assert "..." in r
