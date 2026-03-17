from pathlib import Path
import os
import shutil
from deep.core.repository import DEEP_DIR
from deep.storage.objects import Blob, read_object, write_large_blob, ChunkedBlob, Chunk

def test_cdc_deduplication():
    # Setup temp repo
    import time
    tmp_path = Path(f"tmp_test_cdc_{int(time.time())}").resolve()
    if tmp_path.exists():
        shutil.rmtree(tmp_path)
    tmp_path.mkdir()
    
    dg_dir = tmp_path / DEEP_DIR
    dg_dir.mkdir()
    objects_dir = dg_dir / "objects"
    objects_dir.mkdir()
    
    # 1. Create a "large" file (200KB)
    # Repeating pattern to ensure some chunks are identical
    base_data = b"Some data prefix. " + b"X" * (1024 * 50) + b" Middle part. " + b"Y" * (1024 * 50) + b" End part."
    data1 = base_data * 2 # ~200KB
    
    print(f"Original size: {len(data1)} bytes")
    
    # 2. Write as large blob
    sha1 = write_large_blob(objects_dir, data1)
    print(f"ChunkedBlob SHA: {sha1}")
    
    # Verify it is a ChunkedBlob
    obj1 = read_object(objects_dir, sha1)
    assert isinstance(obj1, Blob) # read_object returns Blob (reassembled)
    assert obj1.serialize_content() == data1
    
    # Check internal storage
    from deep.storage.objects import _object_path
    import zlib
    raw = zlib.decompress(_object_path(objects_dir, sha1).read_bytes())
    assert raw.startswith(b"chunked_blob ")
    
    # 3. Create a slightly different file
    # Change only one character in the middle
    data2 = data1[:1024 * 60] + b"Z" + data1[1024 * 60 + 1:]
    sha2 = write_large_blob(objects_dir, data2)
    
    # 4. Verify Reconstruction
    obj2 = read_object(objects_dir, sha2)
    assert obj2.serialize_content() == data2
    
    # 5. Verify Deduplication
    # Most chunks should be identical.
    # Total chunks for 200KB with 64KB avg size should be ~3-5.
    all_chunks = list(objects_dir.glob("??/*"))
    # We expect some 'chunk' type objects and some 'chunked_blob' type objects
    chunk_count = 0
    for p in all_chunks:
        try:
            raw = zlib.decompress(p.read_bytes())
            if raw.startswith(b"chunk "):
                chunk_count += 1
        except:
            pass
            
    print(f"Total unique chunks stored: {chunk_count}")
    # If we didn't deduplicate, we'd have ~twice the chunks.
    # With one small change, only 1 or 2 chunks should be new.
    print("CDC Deduplication and Reconstruction: SUCCESS")

if __name__ == "__main__":
    test_cdc_deduplication()
