import os
import json
import time
import pytest
from pathlib import Path
from deep.core.locks import BaseLock, STALE_LOCK_THRESHOLD_SECONDS

def test_lock_metadata_writing(tmp_path):
    """Verify that acquire() writes correct JSON metadata."""
    lock_path = tmp_path / "test.lock"
    lock = BaseLock(lock_path)
    
    lock.acquire()
    try:
        assert lock_path.exists()
        data = lock_path.read_text(encoding="utf-8")
        meta = json.loads(data)
        assert meta["pid"] == os.getpid()
        assert "timestamp" in meta
    finally:
        lock.release()

def test_break_dead_pid_lock(tmp_path):
    """Verify that a lock owned by a dead PID is automatically broken."""
    lock_path = tmp_path / "dead_pid.lock"
    
    # Manually create a lock file with a likely dead PID
    # On Windows, PIDs are reuseable but 999999 is usually safe for a short test.
    # Alternatively, get a PID from a finished process.
    import subprocess
    proc = subprocess.Popen(["cmd.exe", "/c", "exit 0"])
    dead_pid = proc.pid
    proc.wait()
    
    metadata = {
        "pid": dead_pid,
        "timestamp": time.time(),
    }
    lock_path.write_text(json.dumps(metadata), encoding="utf-8")
    
    # Try to acquire the same lock path
    new_lock = BaseLock(lock_path, timeout=1.0)
    new_lock.acquire() # Should break the dead lock and succeed
    try:
        data = lock_path.read_text(encoding="utf-8")
        meta = json.loads(data)
        assert meta["pid"] == os.getpid() # Now owned by us
    finally:
        new_lock.release()

def test_break_stale_timestamp_lock(tmp_path):
    """Verify that a lock older than the threshold is automatically broken."""
    lock_path = tmp_path / "stale_ts.lock"
    
    # Create a lock with a very old timestamp
    stale_ts = time.time() - (STALE_LOCK_THRESHOLD_SECONDS + 100)
    metadata = {
        "pid": os.getpid(), # Even if PID is alive, old timestamp should break
        "timestamp": stale_ts,
    }
    lock_path.write_text(json.dumps(metadata), encoding="utf-8")
    
    new_lock = BaseLock(lock_path, timeout=1.0)
    new_lock.acquire() # Should break the stale lock
    try:
        data = lock_path.read_text(encoding="utf-8")
        meta = json.loads(data)
        assert meta["timestamp"] > stale_ts # Refreshed
    finally:
        new_lock.release()

def test_lock_contention_timeout(tmp_path):
    """Ensure lock acquisition fails if held by live process within timeout."""
    lock_path = tmp_path / "contention.lock"
    
    lock1 = BaseLock(lock_path)
    lock1.acquire()
    
    lock2 = BaseLock(lock_path, timeout=0.5)
    with pytest.raises(TimeoutError, match="failed to acquire lock"):
        lock2.acquire()
    
    lock1.release()
