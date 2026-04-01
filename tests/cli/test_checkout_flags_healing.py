import subprocess
import pytest
import os
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

    # Initial commit
    (repo_dir / "f1.txt").write_text("v1")
    run_deep(repo_dir, ["add", "f1.txt"])
    run_deep(repo_dir, ["commit", "-m", "Commit 1"])

    return repo_dir

def test_checkout_branch(repo):
    """Test switching to an existing branch."""
    run_deep(repo, ["branch", "feat"])
    res = run_deep(repo, ["checkout", "feat"])
    assert res.returncode == 0
    assert "switched to branch 'feat'" in res.stdout
    
    # Check HEAD
    res_status = run_deep(repo, ["branch"])
    assert "* feat" in res_status.stdout

def test_checkout_create(repo):
    """Test -b (create and switch)."""
    res = run_deep(repo, ["checkout", "-b", "new_feat"])
    assert res.returncode == 0
    assert "switched to a new branch 'new_feat'" in res.stdout
    
    # Check HEAD
    res_status = run_deep(repo, ["branch"])
    assert "* new_feat" in res_status.stdout

def test_checkout_force(repo):
    """Test -f (force switch with dirty tree)."""
    # Create a branch
    run_deep(repo, ["branch", "feat"])
    
    # Modify f1.txt (dirty)
    (repo / "f1.txt").write_text("v2 dirty")
    run_deep(repo, ["add", "f1.txt"]) # Staged
    
    # Try checkout without force (should fail)
    res_fail = run_deep(repo, ["checkout", "feat"])
    assert res_fail.returncode != 0
    assert "staged changes" in res_fail.stderr
    
    # Try with force
    res_force = run_deep(repo, ["checkout", "-f", "feat"])
    assert res_force.returncode == 0
    assert "switched to branch 'feat'" in res_force.stdout

def test_checkout_file_commit(repo):
    """Test restoring a file from a specific commit."""
    # Commit 1 has f1.txt="v1"
    res_log = run_deep(repo, ["log", "--oneline"])
    sha1 = res_log.stdout.split()[0]
    
    # Modify f1.txt locally
    (repo / "f1.txt").write_text("v2 modified")
    
    # Restore from sha1
    res = run_deep(repo, ["checkout", sha1, "f1.txt"])
    assert res.returncode == 0
    assert "Updated 1 path" in res.stdout
    assert (repo / "f1.txt").read_text() == "v1"

def test_checkout_file_index(repo):
    """Test restoring a file from the index using --."""
    # Commit 1 has f1.txt="v1"
    
    # Stage a change (v2)
    (repo / "f1.txt").write_text("v2 staged")
    run_deep(repo, ["add", "f1.txt"])
    
    # Modify locally again (v3)
    (repo / "f1.txt").write_text("v3 local")
    
    # Restore from index
    res = run_deep(repo, ["checkout", "--", "f1.txt"])
    assert res.returncode == 0
    assert "Updated 1 path from index" in res.stdout
    assert (repo / "f1.txt").read_text() == "v2 staged"
