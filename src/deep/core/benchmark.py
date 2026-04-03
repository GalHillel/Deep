"""
deep.core.benchmark
~~~~~~~~~~~~~~~~~~~~~~~~
Massive-scale performance benchmarking engine for Deep.
Tests limits of Indexing, Object Storage, and DAG traversal.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Dict, Any, List, Tuple

from deep.storage.objects import Blob, Commit, Tree, TreeEntry, write_object
from deep.storage.index import add_multiple_to_index, read_index, DeepIndex
from deep.core.repository import init_repo, DEEP_DIR
from deep.core.status import compute_status
from deep.core.refs import log_history, update_head, resolve_head


def run_benchmarks(verbose: bool = False, compare_git: bool = False) -> Dict[str, Any]:
    """Run a suite of massive-scale project benchmarks and return results."""
    results: Dict[str, Any] = {}
    
    # 1. Setup Temporary Massive Project
    temp_repo_root = Path(tempfile.mkdtemp(prefix="deep_bench_massive_"))
    try:
        init_repo(temp_repo_root)
        dg_dir = temp_repo_root / DEEP_DIR
        objects_dir = dg_dir / "objects"
        
        # --- TEST 1: Massive Indexing (10,000 files) ---
        file_count = 10000
        # Programmatically create files on disk
        start_io = time.perf_counter()
        entries: List[Tuple[str, str, int, int]] = []
        for i in range(file_count):
            rel_path = f"file_{i}.txt"
            f_path = temp_repo_root / rel_path
            content = f"content for file {i}\n".encode()
            f_path.write_bytes(content)
            
            # Prepare index entry info
            stat = f_path.stat()
            # Fast hashing for benchmark (mimic Deep behavior)
            b = Blob(data=content)
            sha = b.sha
            entries.append((rel_path, sha, stat.st_size, stat.st_mtime_ns))
        end_io = time.perf_counter()
        results["worktree_create_10k_time"] = end_io - start_io

        # Measure Indexing Add
        start_idx = time.perf_counter()
        add_multiple_to_index(dg_dir, entries)
        end_idx = time.perf_counter()
        results["index_add_10k_time"] = end_idx - start_idx
        results["index_add_10k_throughput"] = file_count / (end_idx - start_idx)

        # --- TEST 2: Massive Tree Commit (10,000 entries) ---
        start_commit = time.perf_counter()
        tree_entries = []
        for rel_path, sha, _, _ in entries:
            tree_entries.append(TreeEntry(mode="100644", name=rel_path, sha=sha))
        
        tree = Tree(entries=tree_entries)
        tree_sha = tree.write(objects_dir)
        
        commit = Commit(tree_sha=tree_sha, message="Benchmark massive commit", author="Bench <bench@deep>")
        commit_sha = commit.write(objects_dir)
        update_head(dg_dir, commit_sha)
        end_commit = time.perf_counter()
        
        results["commit_10k_tree_time"] = end_commit - start_commit
        results["commit_10k_throughput"] = file_count / (end_commit - start_commit)

        # --- TEST 3: Status Scan Time ---
        # Modify exactly one file to trigger hash check vs MTIME
        mod_path = temp_repo_root / "file_5000.txt"
        mod_path.write_bytes(b"MODIFIED CONTENT\n")
        
        start_status = time.perf_counter()
        # compute_status handles the 10k index vs 10k worktree comparison
        status = compute_status(temp_repo_root)
        end_status = time.perf_counter()
        
        results["status_scan_10k_time"] = end_status - start_status
        # Verify status actually detected the change
        results["status_detected"] = "file_5000.txt" in status.modified

        # --- TEST 4: Deep History Traversal (1,000 commits) ---
        # Build 1,000 linear commits (empty worktree changes to keep it fast)
        parent_sha = commit_sha
        for j in range(1000):
            c = Commit(tree_sha=tree_sha, parent_shas=[parent_sha], message=f"log record {j}")
            parent_sha = c.write(objects_dir)
        
        # Measure traversal
        start_log = time.perf_counter()
        history = log_history(dg_dir, start_sha=parent_sha)
        end_log = time.perf_counter()
        
        results["log_1k_traversal_time"] = end_log - start_log
        results["log_1k_count"] = len(history)

    finally:
        shutil.rmtree(temp_repo_root)

    # Note: legacy (simulated) is removed as per Engineering Mode objectives.
    return results
