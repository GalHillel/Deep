import pytest
import threading
import time
from pathlib import Path

def test_parallel_commits_isolation(repo_factory):
    """Verify multiple parallel commits to independent branches."""
    path = repo_factory.create()
    (path / "base.txt").write_text("root")
    repo_factory.run(["add", "base.txt"], cwd=path)
    repo_factory.run(["commit", "-m", "root"], cwd=path)
    
    def worker(idx):
        bname = f"branch_{idx}"
        repo_factory.run(["checkout", "-b", bname], cwd=path)
        (path / f"file_{idx}.txt").write_text(f"data {idx}")
        repo_factory.run(["add", f"file_{idx}.txt"], cwd=path)
        res = repo_factory.run(["commit", "-m", f"commit {idx}"], cwd=path)
        assert res.returncode == 0

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
        cpath = Path(tempfile.mkdtemp(prefix=f"clone_{idx}_"))
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
        shutil.rmtree(c)
