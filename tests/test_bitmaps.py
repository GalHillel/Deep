import unittest
import os
import shutil
import tempfile
from pathlib import Path
from deep.core.repository import init_repo
from deep.storage.objects import Commit, Tree, TreeEntry, Blob, write_object
from deep.storage.bitmap import generate_pack_bitmaps, BitmapIndex

class TestBitmaps(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.repo_path = self.test_dir / "repo"
        self.dg_dir = init_repo(self.repo_path)
        self.objects_dir = self.dg_dir / "objects"

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def _create_commit(self, message, parents=None):
        blob = Blob(data=f"content for {message}".encode())
        blob_sha = write_object(self.objects_dir, blob)
        tree = Tree(entries=[TreeEntry("file.txt", "100644", blob_sha)])
        tree_sha = write_object(self.objects_dir, tree)
        commit = Commit(tree_sha=tree_sha, parent_shas=parents or [], message=message)
        sha = write_object(self.objects_dir, commit)
        return sha, tree_sha, blob_sha

    def test_bitmap_reachability(self):
        # Create a small history
        c1_sha, t1_sha, b1_sha = self._create_commit("commit 1")
        c2_sha, t2_sha, b2_sha = self._create_commit("commit 2", parents=[c1_sha])
        
        # Pack everything
        from deep.storage.pack import PackWriter
        pw = PackWriter(self.dg_dir)
        # We need all objects
        all_objs = [c1_sha, t1_sha, b1_sha, c2_sha, t2_sha, b2_sha]
        pack_sha, _ = pw.create_pack(all_objs)
        
        # Generate bitmaps
        num_bm = generate_pack_bitmaps(self.dg_dir, pack_sha)
        self.assertEqual(num_bm, 2)
        
        pack_path = self.dg_dir / "objects" / "pack" / f"pack-{pack_sha}.pack"
        bi = BitmapIndex(pack_path)
        
        # Verify reachability from C2
        self.assertTrue(bi.is_reachable(c1_sha, c2_sha))
        self.assertTrue(bi.is_reachable(b1_sha, c2_sha))
        self.assertTrue(bi.is_reachable(b2_sha, c2_sha))
        self.assertTrue(bi.is_reachable(c2_sha, c2_sha))
        
        # Verify reachability from C1 (C2 should NOT be reachable)
        self.assertTrue(bi.is_reachable(b1_sha, c1_sha))
        self.assertFalse(bi.is_reachable(c2_sha, c1_sha))
        self.assertFalse(bi.is_reachable(b2_sha, c1_sha))

if __name__ == "__main__":
    unittest.main()
