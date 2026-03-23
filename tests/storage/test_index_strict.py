import struct
import hashlib
import os
import time
from pathlib import Path
from deep.storage.index import (
    DeepIndex, DeepIndexEntry, read_index, write_index, 
    INDEX_MAGIC_V2, INDEX_VERSION_V2, CorruptIndexError
)

def test_deterministic_read_write_large(tmp_repo):
    """STEP 2.1: Deterministic read/write test with 5000 entries."""
    index = DeepIndex()
    for i in range(5000):
        path = f"dir_{i//100}/file_{i}.txt"
        c_hash = hashlib.sha256(path.encode()).hexdigest()
        p_hash = struct.unpack(">Q", hashlib.sha256(path.encode()).digest()[:8])[0]
        index.entries[path] = DeepIndexEntry(
            content_hash=c_hash,
            mtime_ns=1700000000000 + i,
            size=i * 10,
            path_hash=p_hash
        )
    
    write_index(tmp_repo, index)
    
    # Verify file size is deterministic
    index_file = tmp_repo / "index"
    expected_size = 45 # Header
    for path in index.entries:
        expected_size += 2 + len(path.encode("utf-8")) + 56 # path_len + path + entry_data
    
    assert index_file.stat().st_size == expected_size
    
    # Read back and verify EVERY field
    index2 = read_index(tmp_repo)
    assert len(index2.entries) == 5000
    for path, entry in index.entries.items():
        assert path in index2.entries
        e2 = index2.entries[path]
        assert e2.content_hash == entry.content_hash
        assert e2.mtime_ns == entry.mtime_ns
        assert e2.size == entry.size
        assert e2.path_hash == entry.path_hash

def test_corruption_header_magic(tmp_repo):
    """STEP 2.5: Corruption detection - Invalid Magic."""
    index = DeepIndex()
    index.entries["test.txt"] = DeepIndexEntry("a"*64, 1, 1, 1)
    write_index(tmp_repo, index)
    
    index_file = tmp_repo / "index"
    data = bytearray(index_file.read_bytes())
    data[0:4] = b"BAD!"
    index_file.write_bytes(data)
    
    # Should detect corruption and handle gracefully by moving to .corrupt
    read_index(tmp_repo)
    assert not index_file.exists()
    corrupt_files = list(tmp_repo.glob("index.corrupt.*"))
    assert len(corrupt_files) == 1
    for f in corrupt_files: f.unlink()

def test_corruption_checksum_mismatch(tmp_repo):
    """STEP 2.5: Corruption detection - Checksum mismatch."""
    index = DeepIndex()
    index.entries["test.txt"] = DeepIndexEntry("a"*64, 1, 1, 1)
    write_index(tmp_repo, index)
    
    index_file = tmp_repo / "index"
    data = bytearray(index_file.read_bytes())
    # Header is 45 bytes, checksum is at offset 13 (32 bytes)
    data[13] ^= 0xFF
    index_file.write_bytes(data)
    
    read_index(tmp_repo)
    assert not index_file.exists()
    corrupt_files = list(tmp_repo.glob("index.corrupt.*"))
    assert len(corrupt_files) == 1
    for f in corrupt_files: f.unlink()

def test_partial_write_detection(tmp_repo):
    """STEP 2.6: Partial write detection."""
    index = DeepIndex()
    for i in range(10):
        index.entries[f"file_{i}"] = DeepIndexEntry("a"*64, i, i, i)
    write_index(tmp_repo, index)
    
    index_file = tmp_repo / "index"
    data = index_file.read_bytes()
    
    # Truncate to just after header
    index_file.write_bytes(data[:46])
    
    read_index(tmp_repo)
    assert not index_file.exists()
    corrupt_files = list(tmp_repo.glob("index.corrupt.*"))
    assert len(corrupt_files) == 1
    for f in corrupt_files: f.unlink()

def test_large_file_handling(tmp_repo):
    """STEP 2.7: Large file handling (100k entries)."""
    index = DeepIndex()
    # 100k entries will result in ~10MB index file.
    for i in range(100000):
        path = f"file_{i}.txt"
        index.entries[path] = DeepIndexEntry("a"*64, i, i, i)
    
    start_time = time.time()
    write_index(tmp_repo, index)
    write_dur = time.time() - start_time
    
    start_time = time.time()
    index2 = read_index(tmp_repo)
    read_dur = time.time() - start_time
    
    assert len(index2.entries) == 100000
    # Basic performance sanity (should be < 2s on most modern SSDs)
    assert write_dur < 5.0 
    assert read_dur < 5.0

def test_repeated_open_close_cycles(tmp_repo):
    """STEP 2.8: Repeated open/close cycles (Idempotency)."""
    for i in range(100):
        index = read_index(tmp_repo)
        index.entries[f"cycle_{i}"] = DeepIndexEntry("f"*64, i, i, i)
        write_index(tmp_repo, index)
    
    index_final = read_index(tmp_repo)
    assert len(index_final.entries) == 100
    for i in range(100):
        assert f"cycle_{i}" in index_final.entries

def test_idempotent_reopen(tmp_repo):
    """STEP 2.14: Idempotent re-open."""
    index = DeepIndex()
    index.entries["test"] = DeepIndexEntry("a"*64, 1, 1, 1)
    write_index(tmp_repo, index)
    
    idx1 = read_index(tmp_repo)
    idx2 = read_index(tmp_repo)
    assert idx1.to_binary() == idx2.to_binary()
    assert idx1 == idx2

def test_double_commit_safety(tmp_repo):
    """STEP 2.15: Double commit safety (Writing same index twice)."""
    index = DeepIndex()
    index.entries["test"] = DeepIndexEntry("a"*64, 1, 1, 1)
    
    write_index(tmp_repo, index)
    mtime1 = (tmp_repo / "index").stat().st_mtime_ns
    
    time.sleep(0.01) # Ensure time passes if FS resolution is low
    write_index(tmp_repo, index)
    mtime2 = (tmp_repo / "index").stat().st_mtime_ns
    
    # It should have rewritten the file, so mtime should change (or be same if no-op optimized, 
    # but currently write_index always writes).
    # The point is it shouldn't corrupt.
    idx_final = read_index(tmp_repo)
    assert len(idx_final.entries) == 1
    assert idx_final.entries["test"].content_hash == "a"*64
