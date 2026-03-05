"""
deep.core.benchmark
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

from deep.storage.objects import Blob, Commit, Tree, TreeEntry
from deep.core.repository import init_repo, DEEP_GIT_DIR


def run_benchmarks(verbose: bool = False, compare_git: bool = False) -> Dict[str, Any]:
    """Run a suite of performance benchmarks and return results."""
    results: Dict[str, Any] = {}
    
    # Deep Git Benchmarks
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

    def robust_rmtree(path: Path):
        import shutil
        import stat
        def on_rm_error(func, p, exc_info):
            # p is the path, func is os.unlink or os.rmdir
            os.chmod(p, stat.S_IWRITE)
            func(p)
        shutil.rmtree(path, onerror=on_rm_error)

    if compare_git:
        import subprocess
        git_results = {}
        git_repo = Path(tempfile.mkdtemp(prefix="git_bench_"))
        try:
            # Git Init
            start = time.perf_counter()
            subprocess.run(["git", "init"], cwd=git_repo, capture_output=True, check=True)
            git_results["init_time"] = time.perf_counter() - start
            
            # Git Commit Bench
            start = time.perf_counter()
            for i in range(commit_count):
                f = git_repo / "f.txt"
                f.write_text(f"content {i}")
                subprocess.run(["git", "add", "f.txt"], cwd=git_repo, capture_output=True, check=True)
                subprocess.run(["git", "commit", "-m", f"bench {i}"], cwd=git_repo, capture_output=True, check=True)
            git_results["commit_total_time"] = time.perf_counter() - start
            git_results["commit_avg_time"] = git_results["commit_total_time"] / commit_count
            
            results["git"] = git_results
        except Exception as e:
            results["git_error"] = str(e)
        finally:
            robust_rmtree(git_repo)
            
    return results
