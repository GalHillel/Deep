from pathlib import Path
import os
import shutil
from deep.storage.index import read_index, write_index, IndexEntry, Index
from deep.core.repository import DEEP_DIR

def test_binary_index_migration():
    # Setup temp repo
    tmp_path = Path("tmp_test_index").resolve()
    if tmp_path.exists():
        shutil.rmtree(tmp_path)
    tmp_path.mkdir()
    
    dg_dir = tmp_path / DEEP_DIR
    dg_dir.mkdir()
    
    # 1. Create a JSON index (old format)
    import json
    index_data = {
        "entries": {
            "file1.txt": {"sha": "a"*40, "size": 100, "mtime": 1234.5},
            "dir/file2.txt": {"sha": "b"*40, "size": 200, "mtime": 6789.0}
        }
    }
    (dg_dir / "index").write_text(json.dumps(index_data))
    
    # 2. Read it (should trigger migration)
    index = read_index(dg_dir)
    assert len(index.entries) == 2
    assert index.entries["file1.txt"].sha == "a"*40
    
    # 3. Write it (should be binary)
    write_index(dg_dir, index)
    
    binary_data = (dg_dir / "index").read_bytes()
    assert binary_data.startswith(b"DEEP")
    
    # 4. Read it again (binary)
    index2 = read_index(dg_dir)
    assert index2 == index
    print("Binary index migration and round-trip: SUCCESS")

if __name__ == "__main__":
    test_binary_index_migration()
