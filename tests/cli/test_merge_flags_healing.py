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
    
    # Commit 1
    (repo_dir / "f1.txt").write_text("v1")
    run_deep(repo_dir, ["add", "f1.txt"])
    run_deep(repo_dir, ["commit", "-m", "Commit 1"])
    
    return repo_dir

def test_merge_ff(repo):
    """Test standard fast-forward merge."""
    # Create feature branch from main
    run_deep(repo, ["branch", "feat"])
    run_deep(repo, ["checkout", "feat"])
    
    # Commit on feat
    (repo / "f2.txt").write_text("feat v1")
    run_deep(repo, ["add", "f2.txt"])
    run_deep(repo, ["commit", "-m", "Feat Commit"])
    
    # Switch back to main
    run_deep(repo, ["checkout", "main"])
    
    # Merge feat into main (FF)
    res = run_deep(repo, ["merge", "feat"])
    assert res.returncode == 0
    assert "Fast-forward" in res.stdout
    assert (repo / "f2.txt").exists()

def test_merge_no_ff(repo):
    """Test --no-ff (force merge commit on FF history)."""
    # Create feature branch from main
    run_deep(repo, ["branch", "feat"])
    run_deep(repo, ["checkout", "feat"])
    
    # Commit on feat
    (repo / "f2.txt").write_text("feat v1")
    run_deep(repo, ["add", "f2.txt"])
    run_deep(repo, ["commit", "-m", "Feat Commit"])
    
    # Switch back to main
    run_deep(repo, ["checkout", "main"])
    
    # Merge feat into main with --no-ff
    res = run_deep(repo, ["merge", "--no-ff", "feat"])
    assert res.returncode == 0
    assert "merge made by 3-way merge" in res.stdout
    
    # Verify it has 2 parents
    res_log = run_deep(repo, ["log", "-n", "1"])
    assert "Merge:" in res_log.stdout

def test_merge_3way(repo):
    """Test standard 3-way merge (non-conflicting)."""
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
    
    # Merge feat into main
    run_deep(repo, ["checkout", "main"])
    res = run_deep(repo, ["merge", "feat"])
    assert res.returncode == 0
    assert "merge made by 3-way merge" in res.stdout
    assert (repo / "feat_only.txt").exists()
    assert (repo / "main_only.txt").exists()

def test_merge_abort(repo):
    """Test --abort on a conflicted merge."""
    # Create conflict
    run_deep(repo, ["branch", "feat"])
    
    # Change f1.txt on main
    (repo / "f1.txt").write_text("v1 on main")
    run_deep(repo, ["add", "f1.txt"])
    run_deep(repo, ["commit", "-m", "Conflict Main"])
    
    # Change f1.txt on feat
    run_deep(repo, ["checkout", "feat"])
    (repo / "f1.txt").write_text("v1 on feat")
    run_deep(repo, ["add", "f1.txt"])
    run_deep(repo, ["commit", "-m", "Conflict Feat"])
    
    # Try merge (should conflict)
    run_deep(repo, ["checkout", "main"])
    res_merge = run_deep(repo, ["merge", "feat"])
    assert res_merge.returncode != 0
    assert "CONFLICT" in res_merge.stderr
    
    # Abort
    res_abort = run_deep(repo, ["merge", "--abort"])
    assert res_abort.returncode == 0
    assert "Aborting merge" in res_abort.stdout
    
    # Verify back to clean HEAD
    assert (repo / "f1.txt").read_text() == "v1 on main"
    res_status = run_deep(repo, ["status"])
    assert "working tree clean" in res_status.stdout

def test_merge_no_args(repo):
    """Test merge without branch or --abort."""
    res = run_deep(repo, ["merge"])
    assert res.returncode != 0
    assert "merge branch required" in res.stderr
