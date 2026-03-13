"""
deep.core.benchmark
~~~~~~~~~~~~~~~~~~~~~~~~
Internal benchmarking engine for DeepBridge.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Dict, Any

from deep.storage.objects import Blob, Commit, Tree, TreeEntry
from deep.core.repository import init_repo, DEEP_GIT_DIR


def run_benchmarks(verbose: bool = False, compare_git: bool = False) -> Dict[str, Any]:
    """Run a suite of performance benchmarks and return results."""
    results: Dict[str, Any] = {}
    
    # DeepBridge Benchmarks
    temp_repo_root = Path(tempfile.mkdtemp(prefix="deep_bench_"))
    try:
        init_repo(temp_repo_root)
        dg_dir = temp_repo_root / DEEP_GIT_DIR
        objects_dir = dg_dir / "objects"
        
        # 1. Blob Bench
        blob_count = 100
        blob_data = os.urandom(1024)
        start_time = time.perf_counter()
        for _ in range(blob_count):
            blob = Blob(data=blob_data + os.urandom(8))
            blob.write(objects_dir)
        end_time = time.perf_counter()
        results["deep_blob_total_time"] = end_time - start_time
        results["deep_blob_throughput"] = blob_count / (end_time - start_time)
        
        # 2. Commit Bench
        commit_count = 100
        start_time = time.perf_counter()
        parent_sha = None
        for i in range(commit_count):
            b_sha = Blob(data=f"content {i}".encode()).write(objects_dir)
            t_sha = Tree(entries=[TreeEntry(mode="100644", name="f.txt", sha=b_sha)]).write(objects_dir)
            c = Commit(tree_sha=t_sha, parent_shas=[parent_sha] if parent_sha else [], message=f"bench {i}")
            parent_sha = c.write(objects_dir)
        end_time = time.perf_counter()
        results["deep_commit_total_time"] = end_time - start_time
        results["deep_commit_avg_time"] = (end_time - start_time) / commit_count

    finally:
        shutil.rmtree(temp_repo_root)

    return results
