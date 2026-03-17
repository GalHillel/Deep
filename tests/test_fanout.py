import unittest
import shutil
import tempfile
import os
from pathlib import Path
from deep.storage.objects import Blob, write_object, read_object, walk_loose_shas
from deep.core.repository import init_repo, DEEP_GIT_DIR
from deep.core.maintenance import count_loose_objects

class TestObjectFanout(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.repo_path = self.test_dir / "repo"
        self.dg_dir = init_repo(self.repo_path)
        self.objects_dir = self.dg_dir / "objects"

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_multi_level_sharding(self):
        # 1. Write new object (should be Level 2)
        blob2 = Blob(data=b"level 2 content")
        sha2 = blob2.write(self.objects_dir)
        
        path2 = self.objects_dir / sha2[0:2] / sha2[2:4] / sha2[4:40]
        self.assertTrue(path2.exists(), f"Object {sha2} should be at {path2}")
        
        # 2. Verify read
        obj2 = read_object(self.objects_dir, sha2)
        self.assertEqual(obj2.serialize_content(), b"level 2 content")
        
        # 3. Manually place an object in Level 1 (backward compatibility test)
        from deep.storage.objects import _serialize
        from deep.utils.utils import hash_bytes
        import zlib
        
        raw_content1 = b"level 1 content"
        full_content1 = _serialize("blob", raw_content1)
        sha1 = hash_bytes(full_content1)
        
        path1 = self.objects_dir / sha1[0:2] / sha1[2:40]
        path1.parent.mkdir(parents=True, exist_ok=True)
        path1.write_bytes(zlib.compress(full_content1))
        
        # 4. Verify read Level 1
        obj1 = read_object(self.objects_dir, sha1)
        self.assertEqual(obj1.serialize_content(), b"level 1 content")
        
        # 5. Verify walk
        shas = list(walk_loose_shas(self.objects_dir))
        self.assertIn(sha2, shas)
        self.assertIn(sha1, shas)
        self.assertEqual(len(shas), 2)
        
        # 6. Verify maintenance count
        self.assertEqual(count_loose_objects(self.dg_dir), 2)

if __name__ == "__main__":
    unittest.main()
