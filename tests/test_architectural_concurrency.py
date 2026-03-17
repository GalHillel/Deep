"""
tests.test_architectural_concurrency
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Stress test the TransactionManager and LockManager under high parallelism.
"""

import os
import time
import multiprocessing
from pathlib import Path
import pytest

from deep.commands.init_cmd import run as init_run
from deep.commands.add_cmd import run as add_run
from deep.commands.commit_cmd import run as commit_run
from deep.core.repository import DEEP_GIT_DIR
from deep.storage.objects import read_object, Commit

class Args:
    def __init__(self, message: str, sign: bool = False):
        self.message = message
        self.sign = sign
        self.ai = False
        self.allow_empty = True

def _worker_task(repo_root: Path, worker_id: int, num_commits: int):
    """Worker process that performs multiple commits."""
    os.chdir(repo_root)
    for i in range(num_commits):
        file_path = repo_root / f"worker_{worker_id}.txt"
        file_path.write_text(f"commit {i} from worker {worker_id}")
        
        # Add and commit
        add_run(type("A", (), {"files": [str(file_path)]})())
        try:
            commit_run(Args(f"Worker {worker_id} commit {i}"))
        except Exception as e:
            # Some commits might fail due to lock contention, which is expected 
            # if we don't have infinite retry, but they shouldn't corrupt the repo.
            print(f"Worker {worker_id} commit {i} failed: {e}")
        
        time.sleep(0.01)

def test_high_concurrency_commits(tmp_path: Path):
    """Spawn multiple processes to commit concurrently and verify repo integrity."""
    repo_root = tmp_path
    init_run(type("A", (), {"path": str(repo_root)})())
    
    num_workers = 4
    commits_per_worker = 5
    
    processes = []
    for i in range(num_workers):
        p = multiprocessing.Process(target=_worker_task, args=(repo_root, i, commits_per_worker))
        p.start()
        processes.append(p)
        
    for p in processes:
        p.join()
        
    # Verify integrity
    dg_dir = repo_root / DEEP_GIT_DIR
    from deep.core.refs import resolve_head
    head_sha = resolve_head(dg_dir)
    assert head_sha is not None
    
    # Ensure we can traverse the history
    from deep.core.graph import get_history_graph
    history = get_history_graph(dg_dir, head_sha)
    assert len(history) > 0
    
    # Check that sequence IDs are unique-ish or at least don't crash
    seq_ids = set()
    for node in history:
        commit = node.commit
        assert isinstance(commit, Commit)
        seq_ids.add(commit.sequence_id)
    
    print(f"Total commits in history: {len(history)}")
    print(f"Max sequence ID: {max(seq_ids) if seq_ids else 0}")
