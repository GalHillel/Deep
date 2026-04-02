import unittest
from unittest.mock import patch, MagicMock
import sys
import time
from io import StringIO
from pathlib import Path
from deep.cli.main import main
from deep.core.errors import DeepCLIException

class TestUltraFlagsHealing(unittest.TestCase):
    def setUp(self):
        self.repo_root = Path("C:/fake/repo")
        self.dg_dir = self.repo_root / ".deep"
        
    def test_ultra_help(self):
        """Verify 'deep ultra -h' contains expected examples."""
        with patch("sys.stdout", new=StringIO()) as fake_out:
            with self.assertRaises(SystemExit):
                main(["ultra", "-h"])
            output = fake_out.getvalue()
            self.assertIn("usage: deep ultra", output)
            self.assertIn("⚓️ deep ultra", output)

    @patch("deep.core.repository.find_repo")
    @patch("deep.commands.ultra_cmd.find_repo")
    @patch("deep.core.gc.collect_garbage")
    @patch("deep.storage.objects.walk_loose_shas")
    @patch("deep.storage.pack.PackWriter")
    @patch("deep.storage.commit_graph.build_history_graph")
    def test_ultra_full_cycle(self, mock_cg, mock_pw, mock_walk, mock_gc, mock_find_cmd, mock_find_source):
        """Verify 'deep ultra' executes all three stages of optimization."""
        mock_find_cmd.return_value = self.repo_root
        mock_find_source.return_value = self.repo_root
        mock_gc.return_value = (10, 100) # (removed, kept)
        mock_walk.return_value = ["sha1", "sha2", "sha3", "sha4", "sha5"] # Force repack (>4)
        mock_pw.return_value.create_pack.return_value = ("packhash", "idxhash")
        mock_cg.return_value = 50
        
        with patch("sys.stdout", new=StringIO()) as fake_out:
            main(["ultra"])
            output = fake_out.getvalue()
            
            self.assertIn("⚓️ DEEP ULTRA MODE", output)
            self.assertIn("Stage 1: Garbage Collection", output)
            self.assertIn("Removed 10 unreachable objects", output)
            self.assertIn("Stage 2: Object Repacking", output)
            self.assertIn("Packed 5 objects into pack-packhash.pack", output)
            self.assertIn("Stage 3: Commit Graph Optimization", output)
            self.assertIn("Commit graph rebuilt for 50 commits", output)
            self.assertIn("⚓️ ULTRA COMPLETE", output)
            
            # Verify all core functions were called
            self.assertTrue(mock_gc.called)
            self.assertTrue(mock_pw.called)
            self.assertTrue(mock_cg.called)

    @patch("deep.core.repository.find_repo")
    @patch("deep.commands.ultra_cmd.find_repo")
    @patch("deep.core.gc.collect_garbage")
    @patch("deep.storage.objects.walk_loose_shas")
    @patch("deep.storage.commit_graph.build_history_graph")
    def test_ultra_resilience(self, mock_cg, mock_walk, mock_gc, mock_find_cmd, mock_find_source):
        """Verify 'deep ultra' continues even if a stage fails."""
        mock_find_cmd.return_value = self.repo_root
        mock_find_source.return_value = self.repo_root
        mock_gc.side_effect = RuntimeError("GC FAILED")
        mock_walk.return_value = []
        mock_cg.return_value = 10
        
        with patch("sys.stdout", new=StringIO()) as fake_out:
            main(["ultra"])
            output = fake_out.getvalue()
            
            # Stage 1 failed but 3 should have finished
            self.assertIn("GC stage skipped or failed: GC FAILED", output)
            self.assertIn("Commit graph rebuilt for 10 commits", output)
            self.assertIn("⚓️ ULTRA COMPLETE", output)

    @patch("deep.core.repository.find_repo")
    @patch("deep.commands.ultra_cmd.find_repo")
    def test_ultra_no_repo(self, mock_find_cmd, mock_find_source):
        """Verify 'deep ultra' fails gracefully outside a repository."""
        mock_find_cmd.side_effect = FileNotFoundError("Not a repository")
        mock_find_source.side_effect = FileNotFoundError("Not a repository")
        
        with patch("sys.stdout", new=StringIO()) as fake_out:
            with self.assertRaises(DeepCLIException) as cm:
                main(["ultra"])
            self.assertEqual(cm.exception.code, 1)
            output = fake_out.getvalue()
            self.assertIn("Deep: error: Not a repository", output)

if __name__ == "__main__":
    unittest.main()
