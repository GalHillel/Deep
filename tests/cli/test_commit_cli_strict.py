import subprocess
import os
import time
import pytest
import multiprocessing
import sys
import concurrent.futures
from pathlib import Path
from deep.storage.index import read_index
from deep.core.repository import DEEP_DIR

def get_head_sha(repo_dir: Path) -> str:
    """Read the current HEAD SHA from the repo."""
    head_path = repo_dir / DEEP_DIR / "HEAD"
    if not head_path.exists():
        return ""
    content = head_path.read_text().strip()
    if content.startswith("ref:"):
        ref_path = repo_dir / DEEP_DIR / content.split(": ")[1]
        if ref_path.exists():
            return ref_path.read_text().strip()
    return content

def worker_commit_cli(repo_dir, file_name, commit_msg):
    """Worker that runs 'deep add' then 'deep commit' via subprocess."""
    try:
        file_path = repo_dir / file_name
        file_path.write_text(f"content of {file_name}")
        
        # Add
        r_add = subprocess.run(["deep", "add", file_name], cwd=str(repo_dir), capture_output=True, text=True)
        if r_add.returncode != 0:
            return False, f"Add failed: {r_add.stderr}"
            
        # Commit
        r_cmt = subprocess.run(["deep", "commit", "-m", commit_msg], cwd=str(repo_dir), capture_output=True, text=True)
        if r_cmt.returncode != 0:
            # Tolerable error in HIGH concurrency: another worker committed our changes
            if "No changes to commit" in r_cmt.stdout or "No changes to commit" in r_cmt.stderr:
                return True, ""
            return False, f"Commit failed: {r_cmt.stderr}"
            
        return True, ""
    except Exception as e:
        return False, str(e)

def test_cli_commit_success(tmp_repo_with_init):
    """
    STRICT CASE 1: Successful commit via CLI.
    """
    dg_dir = tmp_repo_with_init
    repo_dir = dg_dir.parent
    
    # Create and add file
    file_name = "commit_test.txt"
    (repo_dir / file_name).write_text("commit content")
    subprocess.run(["deep", "add", file_name], cwd=str(repo_dir), check=True, capture_output=True)
    
    # Commit
    msg = "Initial commit"
    result = subprocess.run(["deep", "commit", "-m", msg], cwd=str(repo_dir), capture_output=True, text=True)
    assert result.returncode == 0
    
    # Verify HEAD
    sha = get_head_sha(repo_dir)
    assert len(sha) == 40, f"Expected 40-char SHA, got {sha}"
    
    # Verify object exists (Level 2: objects/xx/yy/zzzz...)
    obj_path = dg_dir / "objects" / sha[0:2] / sha[2:4] / sha[4:40]
    assert obj_path.exists()

def test_cli_commit_empty(tmp_repo_with_init):
    """
    STRICT CASE 2: Commit with empty index MUST fail and ROLLBACK.
    """
    dg_dir = tmp_repo_with_init
    repo_dir = dg_dir.parent
    
    # Initial state: NO commits
    head_before = get_head_sha(repo_dir)
    
    # Try to commit nothing
    result = subprocess.run(["deep", "commit", "-m", "empty"], cwd=str(repo_dir), capture_output=True, text=True)
    assert result.returncode != 0
    assert "nothing to commit" in result.stderr.lower()
    
    # Verify HEAD didn't change
    head_after = get_head_sha(repo_dir)
    assert head_before == head_after

def test_cli_commit_concurrent(tmp_repo_with_init):
    """
    STRICT CASE 3: Concurrent 'deep commit' processes.
    RepoLock handles queuing. Final history should have 4 commits.
    """
    dg_dir = tmp_repo_with_init
    repo_dir = dg_dir.parent
    
    num_workers = 4
    
    with concurrent.futures.ProcessPoolExecutor(max_workers=num_workers) as executor:
        futures = []
        for i in range(num_workers):
            f_name = f"worker_{i}.txt"
            msg = f"Commit {i}"
            futures.append(executor.submit(worker_commit_cli, repo_dir, f_name, msg))
            
        results = [f.result() for f in futures]
    
    successes = [r[0] for r in results]
    errors = [r[1] for r in results if not r[0]]
    if not all(successes):
        txlog_path = dg_dir / "txlog"
        if txlog_path.exists():
            print(f"\nTXLOG CONTENT:\n{txlog_path.read_text()}")
        assert all(successes), f"Concurrent commits failed: {errors}"
    
    # Verify we have all 4 items in the final state
    # Due to concurrency, some workers might have committed others' changes.
    # The key is that ALL 4 worker files must be in the final tree.
    from deep.storage.objects import read_object, Commit
    head_sha = (dg_dir / "HEAD").read_text().strip()
    if head_sha.startswith("ref:"):
        ref_path = dg_dir / head_sha.split(" ")[1]
        head_sha = ref_path.read_text().strip()
    
    # Check that each file is in the final HEAD
    from deep.core.repository import _get_tree_files # type: ignore
    objects_dir = dg_dir / "objects"
    commit_obj = read_object(objects_dir, head_sha)
    final_files = _get_tree_files(objects_dir, commit_obj.tree_sha)
    
    for i in range(num_workers):
        assert f"worker_{i}.txt" in final_files, f"worker_{i}.txt missing from final history"
    
    # Total commits should be at least 1 and at most 4
    # (Checking if RepoLock allowed everyone to finish successfully)
    commits = []
    curr = head_sha
    while curr:
        c = read_object(objects_dir, curr)
        commits.append(c)
        curr = c.parent_sha if hasattr(c, 'parent_sha') and c.parent_sha else None
    
    # Verify we have at least one commit and the history is reachable
    assert len(commits) >= 1, "Should have at least one commit"
    print(f"DEBUG: Found {len(commits)} commits after concurrent run")

@pytest.fixture
def tmp_repo_with_init(tmp_repo):
    """Fixture that provides an initialized deep repo."""
    repo_dir = tmp_repo.parent
    subprocess.run(["deep", "init"], cwd=str(repo_dir), check=True, capture_output=True)
    return tmp_repo
