import unittest
import os
import shutil
import tempfile
from pathlib import Path
from deep.core.repository import init_repo, checkout
from deep.storage.objects import Blob, write_object
from deep.storage.index import Index, IndexEntry, write_index
from deep.core.status import compute_status

class TestSparseCheckout(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.repo_path = self.test_dir / "repo"
        self.dg_dir = init_repo(self.repo_path)
        self.objects_dir = self.dg_dir / "objects"

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_sparse_checkout_filtering(self):
        # 1. Create a commit with multiple files
        # We'll mock a commit tree for checkout.
        # file1: src/main.py
        # file2: docs/readme.md
        
        sha_main = write_object(self.objects_dir, Blob(data=b"print('hello')"))
        sha_docs = write_object(self.objects_dir, Blob(data=b"read me"))
        
        from deep.storage.objects import Tree, TreeEntry, Commit
        tree = Tree(entries=[
            TreeEntry(mode="100644", name="src/main.py", sha=sha_main),
            TreeEntry(mode="100644", name="docs/readme.md", sha=sha_docs),
        ])
        tree_sha = write_object(self.objects_dir, tree)
        
        commit = Commit(tree_sha=tree_sha, parent_shas=[], author="Test", timestamp=1234567890, message="Initial")
        commit_sha = write_object(self.objects_dir, commit)
        
        # 2. Configure sparse checkout: only 'src/*'
        info_dir = self.dg_dir / "info"
        info_dir.mkdir(parents=True, exist_ok=True)
        (info_dir / "sparse-checkout").write_text("src/*\n", encoding="utf-8")
        
        # 3. Perform checkout
        checkout(self.repo_path, commit_sha, force=True)
        
        # 4. Verify working directory
        self.assertTrue((self.repo_path / "src" / "main.py").exists())
        self.assertFalse((self.repo_path / "docs" / "readme.md").exists())
        
        # 5. Verify status
        status = compute_status(self.repo_path)
        self.assertEqual(len(status.deleted), 0, f"Expected 0 deleted files, got {status.deleted}")
        self.assertEqual(len(status.modified), 0)
        self.assertEqual(len(status.staged_new), 0)
        
        # 6. Verify index flags
        from deep.storage.index import read_index
        index = read_index(self.dg_dir)
        self.assertFalse(index.entries["src/main.py"].skip_worktree)
        self.assertTrue(index.entries["docs/readme.md"].skip_worktree)

if __name__ == "__main__":
    unittest.main()
