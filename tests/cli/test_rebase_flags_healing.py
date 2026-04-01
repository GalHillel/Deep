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
    
    # Commit 1
    (repo_dir / "f1.txt").write_text("v1")
    run_deep(repo_dir, ["add", "f1.txt"])
    run_deep(repo_dir, ["commit", "-m", "Commit 1"])
    
    return repo_dir

def test_rebase_basic(repo):
    """Test standard rebase (moving commits)."""
    # Create feature branch
    run_deep(repo, ["branch", "feat"])
    
    # Commit on main
    (repo / "main_only.txt").write_text("main")
    run_deep(repo, ["add", "main_only.txt"])
    run_deep(repo, ["commit", "-m", "Main Commit"])
    
    # Commit on feat
    run_deep(repo, ["checkout", "feat"])
    (repo / "feat_only.txt").write_text("feat")
    run_deep(repo, ["add", "feat_only.txt"])
    run_deep(repo, ["commit", "-m", "Feat Commit"])
    
    # Rebase feat onto main
    res = run_deep(repo, ["rebase", "main"])
    assert res.returncode == 0
    assert "Successfully rebased" in res.stdout
    
    # Verify history is linear (Feat Commit should have Main Commit as parent)
    res_log = run_deep(repo, ["log", "-n", "2"])
    assert "Feat Commit" in res_log.stdout
    assert "Main Commit" in res_log.stdout

def test_rebase_up_to_date(repo):
    """Test rebase when branch is already on top."""
    res = run_deep(repo, ["rebase", "main"])
    assert res.returncode == 0
    assert "branch is up to date" in res.stdout

def test_rebase_abort_no_active(repo):
    """Test --abort when no rebase is active."""
    res = run_deep(repo, ["rebase", "--abort"])
    assert res.returncode == 0
    assert "No active rebase to abort" in res.stdout

def test_rebase_continue_no_active(repo):
    """Test --continue when no rebase is active."""
    res = run_deep(repo, ["rebase", "--continue"])
    assert res.returncode == 0
    assert "No rebase in progress to continue" in res.stdout

def test_rebase_interactive_stub(repo):
    """Test -i (interactive) placeholder."""
    res = run_deep(repo, ["rebase", "-i", "HEAD"])
    assert res.returncode == 0
    assert "not supported" in res.stdout

def test_rebase_no_args(repo):
    """Test rebase without arguments."""
    res = run_deep(repo, ["rebase"])
    assert res.returncode != 0
    assert "branch (when not using --continue/--abort)" in res.stderr
