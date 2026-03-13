import os
import sys
import shutil
import tempfile
import time
from pathlib import Path

# Add src to sys.path
sys.path.append(os.path.abspath("src"))

from deep.core.repository import init_repo, DEEP_GIT_DIR
from deep.commands import add_cmd, commit_cmd, status_cmd

def log(msg):
    print(f"[*] {msg}")

class Args:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

def run_scale_test():
    with tempfile.TemporaryDirectory() as repo_dir:
        repo_path = Path(repo_dir)
        log(f"Starting Extreme Scale Audit in {repo_path}")
        init_repo(repo_path)
        os.chdir(repo_path)
        
        # 1. Create 100,000 files in deep nested structure
        log("Creating 100,000 files across 100 nested directories...")
        start_time = time.time()
        for d in range(100):
            dir_path = repo_path / f"dir_{d}"
            dir_path.mkdir()
            for f in range(1000):
                (dir_path / f"file_{f}.txt").write_text(f"content_{d}_{f}")
        
        creation_time = time.time() - start_time
        log(f"Creation took {creation_time:.2f}s")
        
        # 2. Add 100,000 files
        log("Staging 100,000 files...")
        start_time = time.time()
        add_cmd.run(Args(files=["."], ai=False, sign=False))
        add_time = time.time() - start_time
        log(f"Staging took {add_time:.2f}s")
        
        # 3. Status Check
        log("Computing status for 100k files...")
        start_time = time.time()
        status_cmd.run(Args())
        status_time = time.time() - start_time
        log(f"Status took {status_time:.2f}s")
        
        # 4. Commit 100,000 files
        log("Committing 100,000 files...")
        start_time = time.time()
        commit_cmd.run(Args(message="Initial commit of 100k files", ai=False, sign=False))
        commit_time = time.time() - start_time
        log(f"Commit took {commit_time:.2f}s")
        
        log("\n--- Audit Results ---")
        log(f"Creation: {creation_time:.2f}s")
        log(f"Staging:  {add_time:.2f}s")
        log(f"Status:   {status_time:.2f}s")
        log(f"Commit:   {commit_time:.2f}s")
        log("---------------------\n")
        log("Phase 10 Completed Successfully")

if __name__ == "__main__":
    run_scale_test()
