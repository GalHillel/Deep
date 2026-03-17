import unittest
import shutil
import tempfile
import time
from pathlib import Path
from deep.storage.objects import Blob, Tree, TreeEntry, Commit, read_object
from deep.core.repository import init_repo, DEEP_DIR
from deep.core.merge import recursive_merge

class TestAdvMerge(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.repo_path = self.test_dir / "repo"
        self.dg_dir = init_repo(self.repo_path)
        self.objects_dir = self.dg_dir / "objects"

    def tearDown(self):
        if hasattr(self, 'test_dir'):
            shutil.rmtree(self.test_dir)

    def create_commit(self, tree_sha, parents, message):
        c = Commit(tree_sha=tree_sha, parent_shas=parents, message=message, timestamp=int(time.time()))
        return c.write(self.objects_dir)

    def create_tree(self, entries):
        t = Tree(entries=entries)
        return t.write(self.objects_dir)

    def create_blob(self, content):
        b = Blob(data=content)
        return b.write(self.objects_dir)

    def test_criss_cross(self):
        # A: initial
        b_init = self.create_blob(b"initial")
        t_a = self.create_tree([TreeEntry(name="common.txt", mode="100644", sha=b_init)])
        sha_a = self.create_commit(t_a, [], "initial")
        
        # B: child of A
        sha_b = self.create_commit(t_a, [sha_a], "B")
        
        # C: child of A
        sha_c = self.create_commit(t_a, [sha_a], "C")
        
        # D: child of B and C, modifies common.txt
        b_d = self.create_blob(b"modified by D")
        t_d = self.create_tree([TreeEntry(name="common.txt", mode="100644", sha=b_d)])
        sha_d = self.create_commit(t_d, [sha_b, sha_c], "D")
        
        # E: child of B and C, adds other.txt
        b_e = self.create_blob(b"added by E")
        t_e = self.create_tree([
            TreeEntry(name="common.txt", mode="100644", sha=b_init),
            TreeEntry(name="other.txt", mode="100644", sha=b_e)
        ])
        sha_e = self.create_commit(t_e, [sha_b, sha_c], "E")
        
        # F: child of D, adds f.txt
        b_f = self.create_blob(b"f")
        t_f = self.create_tree([
            TreeEntry(name="common.txt", mode="100644", sha=b_d),
            TreeEntry(name="f.txt", mode="100644", sha=b_f)
        ])
        sha_f = self.create_commit(t_f, [sha_d], "F")
        
        # G: child of E, adds g.txt
        b_g = self.create_blob(b"g")
        t_g = self.create_tree([
            TreeEntry(name="common.txt", mode="100644", sha=b_init),
            TreeEntry(name="other.txt", mode="100644", sha=b_e),
            TreeEntry(name="g.txt", mode="100644", sha=b_g)
        ])
        sha_g = self.create_commit(t_g, [sha_e], "G")
        
        # Merge F and G. LCAs are D and E.
        merged_sha, conflicts = recursive_merge(self.objects_dir, sha_f, sha_g)
        
        self.assertEqual(conflicts, [])
        merged_tree = read_object(self.objects_dir, merged_sha)
        names = sorted([e.name for e in merged_tree.entries])
        self.assertEqual(names, ["common.txt", "f.txt", "g.txt", "other.txt"])

if __name__ == "__main__":
    unittest.main()
