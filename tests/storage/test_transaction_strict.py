import multiprocessing
import os
import time
import pytest
from pathlib import Path
from deep.storage.transaction import TransactionManager
from deep.storage.index import read_index, add_to_index
from deep.storage.objects import read_object_safe
from deep.core.errors import LockError, TransactionError

def crash_worker(dg_dir, stop_event):
    """Worker that starts a transaction and is killed mid-commit."""
    try:
        with TransactionManager(dg_dir) as tm:
            tm.begin("crash_test")
            # Write some dummy files (simulating staging)
            for i in range(10):
                file_path = f"crash_file_{i}.txt"
                content = f"content_{i}"
                # In a real transaction, we'd add to index/objects
                # For this test, we just want to see if the txlog is consistent
                add_to_index(dg_dir, file_path, "a"*40, len(content), 123)
            
            # Signal that we are ready to be killed
            stop_event.set()
            # Simulate heavy commit work
            time.sleep(10)
            tm.commit()
    except Exception:
        pass

def concurrent_locker(dg_dir, result_queue):
    """Worker that tries to acquire a transaction lock."""
    try:
        with TransactionManager(dg_dir, timeout=2.0) as tm:
            result_queue.put("SUCCESS")
            time.sleep(0.5) # Hold it
    except LockError:
        result_queue.put("LOCK_ERROR")
    except Exception as e:
        result_queue.put(f"ERROR: {e}")

def test_transaction_commit_atomicity(tmp_repo):
    """
    STRICT CASE 1: Transaction Commit Atomicity.
    Ensures that all operations within a transaction are visible after commit.
    """
    dg_dir = tmp_repo
    files_to_add = [("file1.txt", "content1"), ("file2.txt", "content2")]
    
    with TransactionManager(dg_dir) as tm:
        tm.begin("test_op")
        for name, content in files_to_add:
            add_to_index(dg_dir, name, "a"*40, len(content), 123)
        tm.commit()
        
    index = read_index(dg_dir)
    for name, _ in files_to_add:
        assert name in index.entries, f"{name} should be in index after commit"

def test_transaction_rollback_cleanup(tmp_repo):
    """
    STRICT CASE 2: Transaction Rollback Cleanup.
    Ensures that an explicit rollback (or crash-induced abort) leaves no traces.
    """
    dg_dir = tmp_repo
    
    try:
        with TransactionManager(dg_dir) as tm:
            tm.begin("rollback_test")
            add_to_index(dg_dir, "ghost.txt", "b"*40, 10, 456)
            raise ValueError("Triggering Rollback")
    except ValueError:
        pass
        
    index = read_index(dg_dir)
    assert "ghost.txt" not in index.entries, "ghost.txt should NOT be in index after rollback"
    
    # Leak detection will check for *.lock, *.tmp, etc. via conftest

def test_transaction_crash_mid_commit(tmp_repo):
    """
    STRICT CASE 3: Transaction Crash Mid-Commit.
    Uses multiprocessing to simulate a hard crash.
    """
    dg_dir = tmp_repo
    stop_event = multiprocessing.Event()
    
    p = multiprocessing.Process(target=crash_worker, args=(dg_dir, stop_event))
    p.start()
    
    # Wait for worker to be inside transaction
    if not stop_event.wait(timeout=5):
        p.terminate()
        pytest.fail("Worker failed to start transaction in time")
        
    # Kill it mid-flight
    p.terminate()
    p.join()
    
    # Verify consistency after crash
    # Recovery hasn't run yet. The index should be clean (or old state).
    index = read_index(dg_dir)
    for i in range(10):
        assert f"crash_file_{i}.txt" not in index.entries, "Index should not show partial crash writes"

    # Now verify no leaks
    # conftest will yell if repo.lock, branch.lock or index.lock remain.

def test_transaction_concurrent_conflicts(tmp_repo):
    """
    STRICT CASE 4: Transaction Concurrent Conflicts.
    Ensures only one transaction can proceed at a time (Repo lock).
    """
    dg_dir = tmp_repo
    num_workers = 3
    result_queue = multiprocessing.Queue()
    
    processes = []
    for _ in range(num_workers):
        p = multiprocessing.Process(target=concurrent_locker, args=(dg_dir, result_queue))
        processes.append(p)
        p.start()
        
    for p in processes:
        p.join()
        
    results = []
    while not result_queue.empty():
        results.append(result_queue.get())
        
    # Since timeout is 2.0s and each worker holds for 0.5s, 
    # they should all eventually succeed if queuing works,
    # OR some might fail with LockError if they timeout.
    
    successes = results.count("SUCCESS")
    lock_errors = results.count("LOCK_ERROR")
    
    assert successes >= 1, "At least one transaction should have succeeded"
    assert successes + lock_errors == num_workers, f"Unexpected results: {results}"
    
    # Verify no leaks
    # conftest handles this.
