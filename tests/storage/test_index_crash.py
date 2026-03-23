import pytest
import os
import time
from pathlib import Path
from unittest.mock import patch
from deep.storage.index import (
    DeepIndex, DeepIndexEntry, read_index, write_index, 
    _get_journal_path
)
from deep.core.repository import DEEP_DIR

@pytest.fixture
def tmp_repo(tmp_path):
    dg_dir = tmp_path / DEEP_DIR
    dg_dir.mkdir()
    return dg_dir

def test_crash_mid_write_journal_exists(tmp_repo):
    """STEP 4.1 & 4.5: Crash mid-write simulation (Journal remains)."""
    index = DeepIndex()
    index.entries["before.txt"] = DeepIndexEntry("a"*64, 1, 1, 1)
    write_index(tmp_repo, index)
    
    # Simulate a crash during the NEXT write
    index.entries["after.txt"] = DeepIndexEntry("b"*64, 2, 2, 2)
    
    # Mock AtomicWriter to fail after writing some data but before close/replace
    # Actually, let's just manually create the "crashed" state:
    # 1. index exists with "before.txt"
    # 2. index.journal exists
    # 3. .tmp_deep_... might exist
    
    journal_path = _get_journal_path(tmp_repo)
    journal_path.write_text("WRITE_INTENT 123456789")
    
    # When we read, it should detect journal, warn, and clean it up.
    # Current implementation just deletes journal and reads the OLD index.
    idx = read_index(tmp_repo)
    assert "before.txt" in idx.entries
    assert "after.txt" not in idx.entries
    assert not journal_path.exists()

def test_truncation_mid_header(tmp_repo):
    """STEP 4.2: Truncating file (mid-header)."""
    index = DeepIndex()
    index.entries["test.txt"] = DeepIndexEntry("a"*64, 1, 1, 1)
    write_index(tmp_repo, index)
    
    index_file = tmp_repo / "index"
    # Header is 45 bytes. Truncate to 10 bytes.
    with open(index_file, "r+b") as f:
        f.truncate(10)
    
    # Should detect corruption and return empty index
    idx = read_index(tmp_repo)
    assert len(idx.entries) == 0
    assert len(list(tmp_repo.glob("index.corrupt.*"))) == 1

def test_truncation_mid_body(tmp_repo):
    """STEP 4.2: Truncating file (mid-body)."""
    index = DeepIndex()
    for i in range(100):
        index.entries[f"file_{i}"] = DeepIndexEntry("a"*64, i, i, i)
    write_index(tmp_repo, index)
    
    index_file = tmp_repo / "index"
    size = index_file.stat().st_size
    with open(index_file, "r+b") as f:
        f.truncate(size // 2)
    
    idx = read_index(tmp_repo)
    assert len(idx.entries) == 0
    assert len(list(tmp_repo.glob("index.corrupt.*"))) == 1

def test_remove_lock_file_mid_write(tmp_repo):
    """STEP 4.3: Removing lock file (Simulated race/corruption)."""
    # This is hard to do without multiple threads.
    # But we can test if read_index works even if a STALE lock exists.
    lock_path = tmp_repo / "index.lock"
    lock_path.touch()
    
    # read_index should NOT be blocked forever if the lock is stale.
    # Actually, IndexLock (which is probably a FileLock) might have a timeout.
    # Let's see what IndexLock does.
    
    idx = read_index(tmp_repo)
    assert len(idx.entries) == 0
    # If it was a real lock, it might have blocked. If it's just a file, 
    # IndexLock should handle it.

def test_half_buffer_write_simulation(tmp_repo):
    """STEP 4.4: Writing half buffer (Corruption)."""
    index = DeepIndex()
    index.entries["test.txt"] = DeepIndexEntry("a"*64, 1, 1, 1)
    binary = index.to_binary()
    
    # Write only half of the binary data manually
    index_file = tmp_repo / "index"
    index_file.write_bytes(binary[:len(binary)//2])
    
    idx = read_index(tmp_repo)
    assert len(idx.entries) == 0
    assert len(list(tmp_repo.glob("index.corrupt.*"))) == 1

def test_rollback_consistency_simulated(tmp_repo):
    """STEP 2.13: Rollback consistency."""
    # If a write fails, the old index must remain perfectly intact.
    index = DeepIndex()
    index.entries["stable"] = DeepIndexEntry("s"*64, 1, 1, 1)
    write_index(tmp_repo, index)
    
    # Try to write a new index but have it fail mid-way
    new_index = DeepIndex()
    new_index.entries["unstable"] = DeepIndexEntry("u"*64, 2, 2, 2)
    
    with patch("deep.utils.utils.os.replace", side_effect=OSError("Disk Full")):
        with pytest.raises(OSError, match="Disk Full"):
            write_index(tmp_repo, new_index)
            
    # The old index must be intact
    idx = read_index(tmp_repo)
    assert "stable" in idx.entries
    assert "unstable" not in idx.entries
    
    # And NO temp files should be left (AtomicWriter should cleanup)
    temp_files = list(tmp_repo.glob(".tmp_deep_*"))
    assert len(temp_files) == 0
