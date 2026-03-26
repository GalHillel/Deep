import pytest
import threading
import time
import tempfile
import shutil
from pathlib import Path

def test_parallel_commits_isolation(repo_factory):
    """Verify multiple parallel commits to independent branches."""
    path = repo_factory.create()
    (path / "base.txt").write_text("root")
    repo_factory.run(["add", "base.txt"], cwd=path)
    repo_factory.run(["commit", "-m", "root"], cwd=path)
    
    def worker(idx):
        # Create a fresh clone for each worker to ensure worktree isolation
        temp_dir = tempfile.mkdtemp(prefix=f"worker_{idx}_{int(time.time())}_")
        worker_path = Path(temp_dir).resolve()
        try:
            # Retry clone (common contention on Windows when many threads hit the same source)
            for i in range(10):
                res = repo_factory.run(["clone", str(path), str(worker_path)])
                if res.returncode == 0: break
                time.sleep(0.5 * (i + 1))
            else:
                pytest.fail(f"Worker {idx} failed to clone after 10 attempts")

            time.sleep(1.0) # Allow Windows FS to settle more
            
            bname = f"branch_{idx}"
            repo_factory.run(["checkout", "-b", bname], cwd=str(worker_path))
            (worker_path / f"file_{idx}.txt").write_text(f"data {idx}")
            repo_factory.run(["add", f"file_{idx}.txt"], cwd=str(worker_path))
            res = repo_factory.run(["commit", "-m", f"commit {idx}"], cwd=str(worker_path))
            assert res.returncode == 0
            
            # Additional sleep before push to reduce lock contention on Windows
            time.sleep(0.1 * idx)
            
            # Push back to origin to verify coordination (with retries for lock contention)
            for i in range(10):
                res = repo_factory.run(["push", "origin", bname], cwd=str(worker_path))
                if res.returncode == 0: break
                time.sleep(0.2 * (i + 1))
            else:
                pytest.fail(f"Worker {idx} failed to push after 10 attempts")
        finally:
            # Retry deletion if it fails (common on Windows)
            for _ in range(5):
                try:
                    shutil.rmtree(worker_path)
                    break
                except:
                    time.sleep(0.2)

    threads = []
    for i in range(5):
        t = threading.Thread(target=worker, args=(i,))
        threads.append(t)
        t.start()
        
    for t in threads:
        t.join()
        
    res = repo_factory.run(["branch"], cwd=path)
    for i in range(5):
        assert f"branch_{i}" in res.stdout

def test_parallel_clones_stress(repo_factory):
    """Stress test parallel clones from a single source."""
    upstream = repo_factory.create("concurrency_source")
    (upstream / "f.txt").write_text("source data")
    repo_factory.run(["add", "f.txt"], cwd=upstream)
    repo_factory.run(["commit", "-m", "init"], cwd=upstream)
    
    clones = []
    def do_clone(idx):
        temp_dir = tempfile.mkdtemp(prefix=f"clone_{idx}_{int(time.time())}_")
        cpath = Path(temp_dir).resolve()
        res = repo_factory.run(["clone", str(upstream), str(cpath)])
        assert res.returncode == 0
        clones.append(cpath)

    threads = []
    for i in range(10):
        t = threading.Thread(target=do_clone, args=(i,))
        threads.append(t)
        t.start()
        
    for t in threads:
        t.join()
        
    # Cleanup
    for c in clones:
        for _ in range(5):
            try:
                shutil.rmtree(c)
                break
            except:
                time.sleep(0.2)
