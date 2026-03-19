from pathlib import Path
import os
import shutil
from deep.storage.index import read_index, write_index, DeepIndexEntry, DeepIndex
from deep.core.repository import DEEP_DIR

def test_binary_index_migration():
    # Setup temp repo
    tmp_path = Path("tmp_test_index").resolve()
    if tmp_path.exists():
        shutil.rmtree(tmp_path)
    tmp_path.mkdir()
    
    dg_dir = tmp_path / DEEP_DIR
    dg_dir.mkdir()
    
    # 1. Create a legacy index (DEEP format)
    import struct
    # [DEEP][uint32 ver][uint32 count]
    # Entry: [H path_len][20s sha][Q size][d mtime][B flags][path]
    count = 2
    data = b"DEEP" + struct.pack(">II", 1, count)
    
    # file1.txt
    p1 = b"file1.txt"
    sha1 = b"a" * 20
    data += struct.pack(">H20sQdB", len(p1), sha1, 100, 1234.5, 0) + p1
    
    # dir/file2.txt
    p2 = b"dir/file2.txt"
    sha2 = b"b" * 20
    data += struct.pack(">H20sQdB", len(p2), sha2, 200, 6789.0, 0) + p2
    
    (dg_dir / "index").write_bytes(data)
    
    # 2. Read it (should trigger migration)
    index = read_index(dg_dir)
    assert len(index.entries) == 2
    assert index.entries["file1.txt"].content_hash == sha1.hex()
    
    # 3. Write it (should be binary DEEPIDX2)
    write_index(dg_dir, index)
    
    binary_data = (dg_dir / "index").read_bytes()
    assert binary_data.startswith(b"DEEPIDX2")
    
    # 4. Read it again (binary DPIX)
    index2 = read_index(dg_dir)
    assert index2.entries == index.entries
    print("Binary index migration and round-trip: SUCCESS")

if __name__ == "__main__":
    test_binary_index_migration()
