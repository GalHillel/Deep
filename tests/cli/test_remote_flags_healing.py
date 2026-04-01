import subprocess
import pytest
from pathlib import Path

def run_deep(repo_dir, args):
    """Run a deep command and return the result."""
    result = subprocess.run(
        ["deep"] + args,
        cwd=repo_dir,
        capture_output=True,
        text=True
    )
    return result

@pytest.fixture
def repo(tmp_path):
    repo_dir = tmp_path / "test_repo"
    repo_dir.mkdir()
    run_deep(repo_dir, ["init"])
    return repo_dir

def test_remote_list_empty(repo):
    """Test listing remotes when none exist."""
    # Test both 'remote' and 'remote list'
    res1 = run_deep(repo, ["remote"])
    assert res1.returncode == 0
    assert res1.stdout.strip() == ""

    res2 = run_deep(repo, ["remote", "list"])
    assert res2.returncode == 0
    assert res2.stdout.strip() == ""

def test_remote_add_success(repo):
    """Test successfully adding remotes."""
    res = run_deep(repo, ["remote", "add", "origin", "https://github.com/user/repo.git"])
    assert res.returncode == 0
    assert "Added remote 'origin'" in res.stdout

    # Verify listing
    res_list = run_deep(repo, ["remote"])
    assert "origin" in res_list.stdout
    assert "https://github.com/user/repo.git" in res_list.stdout

def test_remote_add_missing_args(repo):
    """Test adding remote with missing arguments."""
    res = run_deep(repo, ["remote", "add", "origin"]) # missing URL
    assert res.returncode != 0
    assert "both remote name and URL are required" in res.stderr

def test_remote_add_duplicate(repo):
    """Test adding a remote that already exists."""
    run_deep(repo, ["remote", "add", "origin", "url1"])
    res = run_deep(repo, ["remote", "add", "origin", "url2"])
    assert res.returncode != 0
    assert "already exists" in res.stderr

def test_remote_remove_success(repo):
    """Test successfully removing a remote."""
    run_deep(repo, ["remote", "add", "origin", "url1"])
    res = run_deep(repo, ["remote", "remove", "origin"])
    assert res.returncode == 0
    assert "Removed remote 'origin'" in res.stdout

    # Verify listing is empty
    res_list = run_deep(repo, ["remote"])
    assert "origin" not in res_list.stdout

def test_remote_remove_not_found(repo):
    """Test removing a non-existent remote."""
    res = run_deep(repo, ["remote", "remove", "ghost"])
    assert res.returncode != 0
    assert "not found" in res.stderr

def test_remote_list_multiple(repo):
    """Test listing multiple remotes alphabetically."""
    run_deep(repo, ["remote", "add", "upstream", "url2"])
    run_deep(repo, ["remote", "add", "origin", "url1"])
    
    res = run_deep(repo, ["remote", "list"])
    assert res.returncode == 0
    lines = res.stdout.strip().splitlines()
    assert len(lines) == 2
    # Alphabetical order: origin then upstream
    assert "origin" in lines[0]
    assert "upstream" in lines[1]
