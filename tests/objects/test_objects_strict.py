import os
import zlib
import time
import multiprocessing
import pytest
from pathlib import Path
from deep.storage.objects import Blob, read_object, CorruptObjectError
from deep.utils.utils import hash_bytes

def test_blob_write_atomicity(tmp_repo):
    """
    STRICT CASE 1: Blob Write Atomicity.
    Ensures that a blob is written correctly and can be read back.
    """
    dg_dir = tmp_repo
    objects_dir = dg_dir / "objects"
    
    content = b"Hello, Deep Storage Hardening!" * 100
    blob = Blob.from_content(content)
    sha = blob.write(objects_dir)
    
    # Assert it exists in the correct fan-out path
    # Default level is 2: objects/xx/yy/zzzz...
    expected_path = objects_dir / sha[0:2] / sha[2:4] / sha[4:40]
    assert expected_path.exists(), f"Object should exist at {expected_path}"
    
    # Read back and verify
    read_blob = read_object(objects_dir, sha)
    assert read_blob.data == content, "Content mismatch after write"
    assert read_blob.sha == sha, "SHA mismatch after read"

def worker_write_blob(objects_dir, content, queue):
    """Worker function for concurrent blob writes."""
    try:
        blob = Blob.from_content(content)
        sha = blob.write(objects_dir)
        queue.put((sha, True))
    except Exception as e:
        queue.put((None, str(e)))

def test_blob_concurrent_writes(tmp_repo):
    """
    STRICT CASE 2: Concurrent Blob Writes.
    Multiple processes writing the exact same content.
    Tests directory creation races and AtomicWriter collisions.
    """
    dg_dir = tmp_repo
    objects_dir = dg_dir / "objects"
    content = b"Concurrent Content" * 50
    expected_sha = hash_bytes(b"blob " + str(len(content)).encode("ascii") + b"\x00" + content)
    
    num_workers = 5
    queue = multiprocessing.Queue()
    processes = []
    
    for i in range(num_workers):
        p = multiprocessing.Process(target=worker_write_blob, args=(objects_dir, content, queue))
        processes.append(p)
        p.start()
        
    for p in processes:
        p.join(timeout=10)
        
    results = []
    while not queue.empty():
        results.append(queue.get())
        
    assert len(results) == num_workers, f"Expected {num_workers} results, got {len(results)}"
    for sha, status in results:
        assert status is True, f"Worker failed: {status}"
        assert sha == expected_sha, f"Worker returned wrong SHA: {sha}"

def crash_worker(objects_dir, data, stop_event):
    """Worker that writes a massive blob and is killed midway."""
    from deep.storage.objects import Blob
    blob = Blob.from_content(data)
    # This will trigger AtomicWriter
    blob.write(objects_dir)

def test_blob_crash_mid_write(tmp_repo):
    """
    STRICT CASE 3: Crash Mid-Write.
    Ensures that partially written blobs do not pollute the object store.
    """
    dg_dir = tmp_repo
    objects_dir = dg_dir / "objects"
    
    # 10MB blob to ensure it takes some time to write
    massive_data = b"A" * (10 * 1024 * 1024)
    expected_sha = hash_bytes(b"blob " + str(len(massive_data)).encode("ascii") + b"\x00" + massive_data)
    
    p = multiprocessing.Process(target=crash_worker, args=(objects_dir, massive_data, None))
    p.start()
    
    # Kill it almost immediately
    time.sleep(0.01) 
    p.terminate()
    p.join()
    
    # The final object path must NOT exist
    expected_path = objects_dir / expected_sha[0:2] / expected_sha[2:4] / expected_sha[4:40]
    assert not expected_path.exists(), "Corrupt/partial blob should not exist at final path after crash"
    
    # Important: The global leak detector in conftest.py will catch any leaked .tmp files.

def test_blob_read_missing_or_corrupt(tmp_repo):
    """
    STRICT CASE 4: Missing or Corrupt Blob.
    Ensures robust error handling for bad disk state.
    """
    dg_dir = tmp_repo
    objects_dir = dg_dir / "objects"
    
    # 1. Missing object
    fake_sha = "a" * 40
    with pytest.raises(FileNotFoundError):
        read_object(objects_dir, fake_sha)
        
    # 2. Corrupted memory (hash mismatch)
    content = b"Corruptible data"
    blob = Blob.from_content(content)
    sha = blob.write(objects_dir)
    path = objects_dir / sha[0:2] / sha[2:4] / sha[4:40]
    
    # Manually flip a byte in the compressed file
    data = bytearray(path.read_bytes())
    data[len(data)//2] ^= 0xFF
    path.write_bytes(bytes(data))
    
    # Should raise CorruptObjectError or ValueError (hash mismatch)
    # Note: deep/storage/objects.py:644 raises ValueError(f"Corrupt object {sha} (hash mismatch).")
    with pytest.raises((CorruptObjectError, ValueError)):
        read_object(objects_dir, sha)
