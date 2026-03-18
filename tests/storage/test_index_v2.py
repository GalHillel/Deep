import pytest
import struct
import hashlib
import os
import shutil
import time
from pathlib import Path
from deep.storage.index import (
    DeepIndex, DeepIndexEntry, read_index, write_index, 
    INDEX_MAGIC_V2, INDEX_VERSION_V2, CorruptIndexError
)
from deep.core.repository import DEEP_DIR

@pytest.fixture
def tmp_repo(tmp_path):
    dg_dir = tmp_path / DEEP_DIR
    dg_dir.mkdir()
    return dg_dir

def test_index_v2_roundtrip(tmp_repo):
    """Test basic serialization and deserialization of a large index."""
    index = DeepIndex()
    for i in range(1001):
        path = f"file_{i}.txt"
        content_hash = hashlib.sha256(path.encode()).hexdigest()
        path_hash = struct.unpack(">Q", hashlib.sha256(path.encode()).digest()[:8])[0]
        index.entries[path] = DeepIndexEntry(
            content_hash=content_hash,
            mtime_ns=1700000000000 + i,
            size=1024 + i,
            path_hash=path_hash
        )
    
    write_index(tmp_repo, index)
    
    # 1. Check file exists and has correct magic
    index_file = tmp_repo / "index"
    assert index_file.exists()
    data = index_file.read_bytes()
    assert data.startswith(INDEX_MAGIC_V2)
    
    # 2. Read back
    index2 = read_index(tmp_repo)
    assert len(index2.entries) == 1001
    assert index2.entries["file_500.txt"].content_hash == hashlib.sha256(b"file_500.txt").hexdigest()
    assert index2.entries["file_500.txt"].path_hash == struct.unpack(">Q", hashlib.sha256(b"file_500.txt").digest()[:8])[0]

def test_index_corruption_detection(tmp_repo):
    """Test detection of random bit flips/corruption."""
    index = DeepIndex()
    index.entries["test.txt"] = DeepIndexEntry(
        content_hash="a" * 64,
        mtime_ns=12345,
        size=1024,
        path_hash=67890
    )
    write_index(tmp_repo, index)
    
    index_file = tmp_repo / "index"
    data = bytearray(index_file.read_bytes())
    
    # Flip a bit in the body (after 45 bytes header)
    data[50] = data[50] ^ 0xFF 
    index_file.write_bytes(data)
    
    # read_index should detect corruption, move file, and return empty index
    index_recovered = read_index(tmp_repo)
    assert len(index_recovered.entries) == 0
    
    # Check if corrupted file was moved
    corrupt_files = list(tmp_repo.glob("index.corrupt.*"))
    assert len(corrupt_files) == 1

def test_index_partial_write_recovery(tmp_repo):
    """Test recovery from truncated/partial index files."""
    index = DeepIndex()
    index.entries["test.txt"] = DeepIndexEntry("b" * 64, 1, 2048, 1)
    write_index(tmp_repo, index)
    
    index_file = tmp_repo / "index"
    data = index_file.read_bytes()
    
    # Truncate file halfway
    index_file.write_bytes(data[:len(data)//2])
    
    index_recovered = read_index(tmp_repo)
    assert len(index_recovered.entries) == 0
    assert len(list(tmp_repo.glob("index.corrupt.*"))) == 1

def test_index_checksum_mismatch(tmp_repo):
    """Test explicit checksum mismatch detection."""
    index = DeepIndex()
    index.entries["valid.txt"] = DeepIndexEntry("c"*64, 1, 4096, 1)
    write_index(tmp_repo, index)
    
    index_file = tmp_repo / "index"
    data = bytearray(index_file.read_bytes())
    
    # Corrupt the checksum in the header (bytes 13 to 45)
    data[20] = data[20] ^ 0xFF
    index_file.write_bytes(data)
    
    with pytest.raises(CorruptIndexError, match="checksum mismatch"):
        # We use from_binary directly to see the exception
        DeepIndex.from_binary(index_file.read_bytes())
    
    # read_index should handle it gracefully
    idx = read_index(tmp_repo)
    assert len(idx.entries) == 0

def test_index_v1_migration(tmp_repo):
    """Test migration from v1 (DPIX) format."""
    # [DPIX][VER 1][COUNT 1][FLAGS 0] = 16B
    # v1 Entry (62B + path): [P_HASH 20s][MTIME Q][SIZE Q][C_HASH 20s][FLAGS I][P_LEN H][path]
    p_hash = hashlib.sha1(b"v1_file.txt").digest()
    c_hash = b"\xde\xad\xbe\xef" * 5 # 20 bytes
    path = b"v1_file.txt"
    
    header = b"DPIX" + struct.pack(">III", 1, 1, 0)
    entry = p_hash + struct.pack(">QQ", 123456789, 1000) + c_hash + struct.pack(">IH", 0, len(path)) + path
    
    (tmp_repo / "index").write_bytes(header + entry)
    
    index = read_index(tmp_repo)
    assert len(index.entries) == 1
    assert "v1_file.txt" in index.entries
    assert index.entries["v1_file.txt"].mtime_ns == 123456789
    assert index.entries["v1_file.txt"].size == 1000
    # v2 content_hash should be padded SHA1
    assert index.entries["v1_file.txt"].content_hash.startswith(c_hash.hex())
    
    # Verify it was rewritten to v2
    data = (tmp_repo / "index").read_bytes()
    assert data.startswith(INDEX_MAGIC_V2)

def test_index_journal_cleanup(tmp_repo):
    """Test that a stale journal is cleaned up on read."""
    journal_path = tmp_repo / "index.journal"
    journal_path.write_text("STALE_JOURNAL")
    
    assert journal_path.exists()
    read_index(tmp_repo)
    assert not journal_path.exists()

def test_index_deterministic_output(tmp_repo):
    """Ensure same input results in same binary output."""
    hash_a = "a" * 64
    hash_b = "b" * 64
    index1 = DeepIndex()
    index1.entries["b.txt"] = DeepIndexEntry(hash_b, 2, 5000, 2)
    index1.entries["a.txt"] = DeepIndexEntry(hash_a, 1, 5000, 1)
    
    index2 = DeepIndex()
    index2.entries["a.txt"] = DeepIndexEntry(hash_a, 1, 5000, 1)
    index2.entries["b.txt"] = DeepIndexEntry(hash_b, 2, 5000, 2)
    
    assert index1.to_binary() == index2.to_binary()
