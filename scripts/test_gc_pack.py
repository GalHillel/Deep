from pathlib import Path
import os
import shutil
import subprocess
import sys
from deep_git.core.repository import DEEP_GIT_DIR, find_repo
from deep_git.core.objects import Blob, write_object, read_object
from deep_git.core.gc import collect_garbage

def test_packfile_compaction():
    # Setup unique temp repo
    import time
    tmp_path = Path(f"tmp_test_gc_{int(time.time())}").resolve()
    
    def cleanup():
        if tmp_path.exists():
            for _ in range(5):
                try:
                    shutil.rmtree(tmp_path)
                    break
                except PermissionError:
                    time.sleep(0.5)
    
    cleanup()
    tmp_path.mkdir()
    
    dg_dir = tmp_path / DEEP_GIT_DIR
    dg_dir.mkdir()
    objects_dir = dg_dir / "objects"
    objects_dir.mkdir()
    (dg_dir / "refs" / "heads").mkdir(parents=True)
    (dg_dir / "refs" / "tags").mkdir(parents=True)
    
    # 1. Create some loose objects
    blob_content = b"Object 1 content"
    sha1 = write_object(objects_dir, Blob(blob_content))
    print(f"Created SHA1: {sha1}")
    
    # 2. Make it "reachable" by creating a branch head
    head_path = dg_dir / "refs" / "heads" / "main"
    head_path.write_text(sha1)
    (dg_dir / "HEAD").write_text("ref: refs/heads/main")
    
    # Verify it is loose
    loose_path = objects_dir / sha1[:2] / sha1[2:]
    assert loose_path.exists()
    
    # 3. Run GC logic directly
    print("\nRunning collect_garbage...")
    unreachable, total = collect_garbage(tmp_path, dry_run=False, verbose=True)
    print(f"GC done. Unreachable: {unreachable}, Total: {total}")
    
    # 4. Verify loose are gone and pack exists
    assert not loose_path.exists()
    pack_dir = objects_dir / "pack"
    assert pack_dir.exists()
    packs = list(pack_dir.glob("*.pack"))
    assert len(packs) > 0
    print(f"Packs found: {[p.name for p in packs]}")
    
    # 5. Verify we can still read them (this tests PackReader integration in objects.py)
    data1 = read_object(objects_dir, sha1).serialize_content()
    assert data1 == blob_content
    print("Verification: Can read objects from packfile!")
    
    print("\nPackfile Compaction: SUCCESS")

if __name__ == "__main__":
    test_packfile_compaction()
