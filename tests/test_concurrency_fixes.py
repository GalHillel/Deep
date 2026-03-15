import os
import time
import json
import threading
import uuid
import pytest
from pathlib import Path
from deep.storage.txlog import TransactionLog, TxRecord
from deep.core.locks import BaseLock, RepositoryLock
from deep.utils.utils import AtomicWriter

def test_tx_id_uniqueness(tmp_path):
    txlog = TransactionLog(tmp_path)
    tx_ids = set()
    for _ in range(100):
        tx_id = txlog.begin("test_op")
        assert tx_id not in tx_ids
        tx_ids.add(tx_id)
        # Verify format: test_op_timestamp_uuid (4 parts because of test_op)
        parts = tx_id.split("_")
        assert len(parts) == 4
        assert parts[0] == "test"
        assert parts[1] == "op"
        assert len(parts[3]) == 8

def test_concurrent_wal_append(tmp_path):
    txlog = TransactionLog(tmp_path)
    num_threads = 8
    records_per_thread = 15 # Reduced slightly for Windows stability
    
    exceptions = []
    def worker():
        try:
            for i in range(records_per_thread):
                txlog.begin(f"thread_{threading.get_ident()}", details=f"record_{i}")
        except Exception as e:
            exceptions.append(e)

    threads = [threading.Thread(target=worker) for _ in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
        
    if exceptions:
        pytest.fail(f"Threads failed with: {exceptions}")

    records = txlog.read_all()
    assert len(records) == num_threads * records_per_thread
    
    # Verify no data corruption
    tx_ids = [r.tx_id for r in records]
    assert len(set(tx_ids)) == len(tx_ids)

def test_lock_contention(tmp_path):
    lock_path = tmp_path / "test.lock"
    lock1 = BaseLock(lock_path)
    lock1.acquire()
    
    # Attempt to acquire the same lock from a different instance - it should FAIL
    lock2 = BaseLock(lock_path, timeout=0.1)
    with pytest.raises(TimeoutError):
        lock2.acquire()
    
    lock1.release()
    
    # Now lock2 should be able to acquire it
    lock2.acquire()
    lock2.release()

if __name__ == "__main__":
    # Manually run if needed
    pass
