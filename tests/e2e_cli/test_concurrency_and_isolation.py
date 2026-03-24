import pytest
import threading

def test_concurrency_global_config(repo_factory):
    """Test concurrent global config modification with isolated environment."""
    path = repo_factory.create("concurrency_test")
    
    def worker(i):
        # We must use repo_factory.run to ensure isolation in each thread
        repo_factory.run(["config", "--global", "user.name", f"User_{i}"], cwd=path)
    
    threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
    for t in threads: t.start()
    for t in threads: t.join()
    
    # Final check
    res = repo_factory.run(["config", "--global", "user.name"], cwd=path)
    assert res.returncode == 0
    # One of the values should be there
    assert "User_" in res.stdout
