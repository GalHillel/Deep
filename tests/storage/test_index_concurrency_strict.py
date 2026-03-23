import multiprocessing
import os
import time
import random
from pathlib import Path
from deep.storage.index import (
    read_index, add_to_index, DeepIndex
)

def slow_writer(dg_dir: Path, stop_event: multiprocessing.Event):
    """Slow writer that holds the lock."""
    import time
    from deep.storage.index import add_to_index
    from deep.core.locks import IndexLock
    lock = IndexLock(dg_dir)
    with lock:
        # Add one entry
        add_to_index(dg_dir, "slow.txt", "a"*40, 1, 1)
        # Hold lock until signaled
        stop_event.wait(5)

def worker_add_entries(dg_dir: Path, worker_id: int, count: int, result_queue: multiprocessing.Queue):
    """Worker process to add multiple entries to the index."""
    try:
        for i in range(count):
            path = f"worker_{worker_id}_file_{i}.txt"
            sha = f"{worker_id:02x}" * 20
            add_to_index(dg_dir, path, sha, i, int(time.time() * 1e9))
            # Random slight delay to increase contention
            time.sleep(random.uniform(0.001, 0.01))
        result_queue.put(True)
    except Exception as e:
        result_queue.put(f"Worker {worker_id} failed: {e}")

def test_concurrent_multiprocessing_writes(tmp_repo):
    """STEP 3.2: Simultaneous writers using multiprocessing."""
    num_workers = 4
    entries_per_worker = 50
    queue = multiprocessing.Queue()
    
    processes = []
    for i in range(num_workers):
        p = multiprocessing.Process(
            target=worker_add_entries, 
            args=(tmp_repo, i, entries_per_worker, queue)
        )
        processes.append(p)
        p.start()
        
    for p in processes:
        p.join(timeout=30)
        
    # Check for errors
    results = []
    while not queue.empty():
        results.append(queue.get())
        
    for res in results:
        assert res is True, res
        
    # Verify all entries are present
    index = read_index(tmp_repo)
    assert len(index.entries) == num_workers * entries_per_worker
    for w in range(num_workers):
        for i in range(entries_per_worker):
            assert f"worker_{w}_file_{i}.txt" in index.entries

def test_reader_during_write(tmp_repo):
    """STEP 3.5: Reader during write."""
    # Start a slow writer process that holds the lock for a bit
    stop_event = multiprocessing.Event()
    p = multiprocessing.Process(target=slow_writer, args=(tmp_repo, stop_event))
    p.start()
    
    time.sleep(0.5) # Give it time to acquire lock
    
    # Try reading. read_index SHOULD be able to read even if locked?
    # Actually, read_index in index.py DOES acquire a lock:
    # 284: lock = IndexLock(dg_dir)
    # 285: with lock:
    # So it WILL block.
    
    start = time.time()
    # This should block until slow_writer releases or times out (10s default)
    stop_event.set() # Signal to release
    index = read_index(tmp_repo)
    duration = time.time() - start
    
    assert "slow.txt" in index.entries
    p.join()

def test_stale_lock_recovery(tmp_repo):
    """STEP 2.4: Stale lock recovery (Real Dead PID)."""
    import subprocess
    import sys
    import json
    
    # Spawn and kill a dummy process to get a definitively dead PID
    p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(10)"])
    pid = p.pid
    p.terminate()
    p.wait()
    
    lock_path = tmp_repo / "index.lock"
    metadata = {
        "pid": pid,
        "timestamp": time.time() - 100,
        "hostname": "test"
    }
    # Write metadata at beginning
    with open(lock_path, "w") as f:
        f.write(json.dumps(metadata).ljust(1000))
    
    # Try reading. It should break the stale lock and proceed.
    index = read_index(tmp_repo)
    assert len(index.entries) == 0
    # The lock file might still exist if read_index acquired its own, 
    # but the point is it shouldn't timeout.

def test_thread_contention_mixed(tmp_repo):
    """STEP 2.9: Thread contention (mixed read/write)."""
    import threading
    num_threads = 10
    loops = 20
    errors = []
    
    def worker():
        try:
            for i in range(loops):
                if random.random() > 0.5:
                    add_to_index(tmp_repo, f"thread_{threading.get_ident()}_{i}", "a"*40, i, i)
                else:
                    read_index(tmp_repo)
        except Exception as e:
            errors.append(e)
            
    threads = [threading.Thread(target=worker) for _ in range(num_threads)]
    for t in threads: t.start()
    for t in threads: t.join()
    
    assert not errors, f"Errors: {errors}"
