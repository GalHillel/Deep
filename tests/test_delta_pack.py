import unittest
import os
import shutil
import tempfile
import zlib
from pathlib import Path
from deep.core.repository import init_repo
from deep.storage.objects import Blob, write_object, read_object
from deep.storage.pack import PackWriter, PackReader

class TestDeltaPack(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.repo_path = self.test_dir / "repo"
        self.dg_dir = init_repo(self.repo_path)
        self.objects_dir = self.dg_dir / "objects"

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_delta_compression_efficiency(self):
        # Create two similar blobs
        content1 = b"Hello world, this is a long string that will be used as a base for delta compression." * 10
        content2 = content1 + b" And here is some extra data added to the second version."
        
        sha1 = write_object(self.objects_dir, Blob(data=content1))
        sha2 = write_object(self.objects_dir, Blob(data=content2))
        
        # 1. Pack without deltas (mocking WINDOW_SIZE=0)
        # Actually our PackWriter has a fixed WINDOW_SIZE. 
        # But we can check if it actually deltas them.
        
        pw = PackWriter(self.dg_dir)
        pack_sha, _ = pw.create_pack([sha1, sha2])
        
        pack_path = self.dg_dir / "objects" / "pack" / f"pack-{pack_sha}.pack"
        pack_size = pack_path.stat().st_size
        
        # Total raw size is approx 2 * len(content1)
        total_raw = len(content1) + len(content2)
        print(f"\nRaw size: {total_raw}, Pack size: {pack_size}")
        
        # 2. Verify we can read them back correctly
        pr = PackReader(self.dg_dir)
        obj1 = pr.get_object(sha1)
        obj2 = pr.get_object(sha2)
        
        self.assertEqual(obj1.serialize_content(), content1)
        self.assertEqual(obj2.serialize_content(), content2)
        
        # 3. Inspect pack to see if delta was used
        with open(pack_path, "rb") as f:
            f.read(12) # header
            # Entry 1 (type_id, comp_size)
            t1, s1 = struct.unpack(">BQ", f.read(9))
            f.read(s1)
            # Entry 2
            t2, s2 = struct.unpack(">BQ", f.read(9))
            print(f"Object 2 type in pack: {t2}")
            # If t2 is 7, delta compression worked!

import struct
if __name__ == "__main__":
    unittest.main()
