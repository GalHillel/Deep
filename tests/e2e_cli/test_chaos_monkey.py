import random
import time
import pytest
import threading
from pathlib import Path

def test_random_chaos_mutation(repo_factory):
    """Perform a random sequence of operations under isolation."""
    path = repo_factory.create()
    files = []
    
    for i in range(50):
        op = random.choice(["add", "modify", "mv", "rm", "commit", "status"])
        
        if op == "add" or (op == "modify" and not files):
            filename = f"file_{random.randint(0, 1000)}.txt"
            (path / filename).write_text(f"content {random.random()}")
            repo_factory.run(["add", filename], cwd=path)
            if filename not in files: files.append(filename)
            
        elif op == "modify" and files:
            filename = random.choice(files)
            if (path / filename).exists():
                with open(path / filename, "a") as f:
                    f.write(f"\nmore content {random.random()}")
                repo_factory.run(["add", filename], cwd=path)
                
        elif op == "mv" and files:
            old_name = random.choice(files)
            if (path / old_name).exists():
                new_name = f"moved_{old_name}"
                repo_factory.run(["mv", old_name, new_name], cwd=path)
                files.remove(old_name)
                files.append(new_name)
                
        elif op == "rm" and files:
            filename = random.choice(files)
            if (path / filename).exists():
                repo_factory.run(["rm", filename], cwd=path)
                files.remove(filename)
                
        elif op == "commit":
            repo_factory.run(["commit", "-m", f"chaos commit {i}"], cwd=path)
            
        elif op == "status":
            res = repo_factory.run(["status"], cwd=path)
            assert res.returncode == 0

    # Final verification
    res = repo_factory.run(["fsck"], cwd=path)
    assert res.returncode == 0
    res = repo_factory.run(["doctor"], cwd=path)
    assert res.returncode == 0

def test_concurrent_chaos_conflicts(repo_factory):
    """Force concurrent modifications to same files using isolated repo_factory."""
    path = repo_factory.create()
    (path / "conflict.txt").write_text("initial")
    repo_factory.run(["add", "conflict.txt"], cwd=path)
    repo_factory.run(["commit", "-m", "initial"], cwd=path)
    
    def worker(branch_name, content):
        repo_factory.run(["checkout", "-b", branch_name], cwd=path)
        with open(path / "conflict.txt", "w") as f:
            f.write(content)
        repo_factory.run(["add", "conflict.txt"], cwd=path)
        repo_factory.run(["commit", "-m", f"edit from {branch_name}"], cwd=path)
        repo_factory.run(["checkout", "main"], cwd=path)

    threads = []
    for i in range(5):
        t = threading.Thread(target=worker, args=(f"branch_{i}", f"content {i}"))
        threads.append(t)
        t.start()
        
    for t in threads:
        t.join()

    # Try to merge everyone into main
    for i in range(5):
        res = repo_factory.run(["merge", f"branch_{i}"], cwd=path)
        assert res.returncode in [0, 1]
        
        if "CONFLICT" in res.stdout:
            (path / "conflict.txt").write_text(f"resolved {i}")
            repo_factory.run(["add", "conflict.txt"], cwd=path)
            repo_factory.run(["commit", "-m", f"resolved merge {i}"], cwd=path)

    res = repo_factory.run(["verify"], cwd=path)
    assert res.returncode == 0

