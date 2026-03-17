import unittest
import os
import shutil
import tempfile
import time
from pathlib import Path
from deep.core.repository import init_repo, DEEP_GIT_DIR
from deep.storage.objects import Commit, Tree, TreeEntry, Blob, write_object
from deep.core.graph import get_history_graph
from deep.storage.commit_graph import write_repository_commit_graph, CommitGraph

class TestCommitGraph(unittest.TestCase):
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
        return write_object(self.objects_dir, commit)

    def test_graph_consistency(self):
        # Create a linear history of 10 commits
        last_sha = None
        for i in range(10):
            last_sha = self._create_commit(f"commit {i}", parents=[last_sha] if last_sha else [])

        # Get graph WITHOUT index
        graph_no_index = get_history_graph(self.dg_dir, all_refs=True)
        
        # Write index
        num = write_repository_commit_graph(self.dg_dir)
        self.assertEqual(num, 10)
        
        # Get graph WITH index
        graph_with_index = get_history_graph(self.dg_dir, all_refs=True)
        
        self.assertEqual(len(graph_no_index), len(graph_with_index))
        shas_no = {n.sha for n in graph_no_index}
        shas_with = {n.sha for n in graph_with_index}
        self.assertEqual(shas_no, shas_with)

    def test_large_graph_performance(self):
        # Create 100 commits
        last_sha = None
        for i in range(100):
            last_sha = self._create_commit(f"commit {i}", parents=[last_sha] if last_sha else [])
            
        # Time without index
        start = time.perf_counter()
        get_history_graph(self.dg_dir, all_refs=True)
        dur_no = time.perf_counter() - start
        
        write_repository_commit_graph(self.dg_dir)
        
        # Time with index
        start = time.perf_counter()
        get_history_graph(self.dg_dir, all_refs=True)
        dur_with = time.perf_counter() - start
        
        print(f"\nTraversal (100 commits): No Index={dur_no:.4f}s, With Index={dur_with:.4f}s")
        # In this small case, dur_with might be similar due to overhead, but should not be significantly worse.
        # In real Git, the speedup is 2-10x for large repos.

if __name__ == "__main__":
    unittest.main()
