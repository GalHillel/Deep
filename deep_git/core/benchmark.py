"""
deep_git.core.benchmark
~~~~~~~~~~~~~~~~~~~~~~~~
Internal benchmarking engine for Deep Git.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Dict, Any

from deep_git.core.objects import Blob, Commit, Tree, TreeEntry
from deep_git.core.repository import init_repo, DEEP_GIT_DIR


def run_benchmarks(verbose: bool = False) -> Dict[str, Any]:
    """Run a suite of performance benchmarks and return results."""
    results: Dict[str, Any] = {}
    
    # Use a temporary directory for the benchmark repo
    temp_repo_root = Path(tempfile.mkdtemp(prefix="deepgit_bench_"))
    try:
        init_repo(temp_repo_root)
        dg_dir = temp_repo_root / DEEP_GIT_DIR
        objects_dir = dg_dir / "objects"
        
        # 1. Blob Bench (Hashing & Writing)
        blob_count = 100
        blob_data = os.urandom(1024)  # 1KB of random data
        start_time = time.perf_counter()
        for _ in range(blob_count):
            # Slightly vary data to avoid deduplication if we wanted to measure real write speed
            # But SHA-1 collision is what we mostly measure.
            blob = Blob(data=blob_data + os.urandom(8))
            blob.write(objects_dir)
        end_time = time.perf_counter()
        results["blob_throughput"] = blob_count / (end_time - start_time)
        results["blob_total_time"] = end_time - start_time
        
        # 2. Commit Bench (DAG creation)
        commit_count = 100
        start_time = time.perf_counter()
        parent_sha = None
        for i in range(commit_count):
            from deep_git.core.index import Index, IndexEntry, write_index
            # Create a simple tree
            b = Blob(data=f"content {i}".encode())
            b_sha = b.write(objects_dir)
            t = Tree(entries=[TreeEntry(mode="100644", name="f.txt", sha=b_sha)])
            t_sha = t.write(objects_dir)
            
            c = Commit(
                tree_sha=t_sha,
                parent_shas=[parent_sha] if parent_sha else [],
                message=f"benchmark {i}"
            )
            parent_sha = c.write(objects_dir)
        end_time = time.perf_counter()
        results["commit_avg_time"] = (end_time - start_time) / commit_count
        results["commit_total_time"] = end_time - start_time
        
        # 3. Index Bench (Large tree simulation)
        file_count = 500
        start_time = time.perf_counter()
        from deep_git.core.index import Index, IndexEntry, write_index
        idx = Index()
        for i in range(file_count):
            idx.entries[f"file_{i}.txt"] = IndexEntry(
                sha="0" * 40,
                size=123,
                mtime=int(time.time()),
            )
        write_index(dg_dir, idx)
        end_time = time.perf_counter()
        results["index_write_time"] = end_time - start_time
        results["index_file_count"] = file_count

    finally:
        shutil.rmtree(temp_repo_root)
        
    return results
