import unittest
from unittest.mock import patch, MagicMock
import sys
from io import StringIO
from pathlib import Path
from deep.cli.main import main
from deep.core.errors import DeepCLIException

class TestGcFlagsHealing(unittest.TestCase):
    def setUp(self):
        self.repo_root = Path("C:/fake/repo")
        self.dg_dir = self.repo_root / ".deep"
        
    def test_gc_help(self):
        """Verify 'deep gc -h' contains expected flags."""
        with patch("sys.stdout", new=StringIO()) as fake_out:
            with self.assertRaises(SystemExit):
                main(["gc", "-h"])
            output = fake_out.getvalue()
            self.assertIn("usage: deep gc", output)
            self.assertIn("--dry-run", output)
            self.assertIn("--prune PRUNE", output)
            self.assertIn("⚓️ deep gc", output)

    @patch("deep.commands.gc_cmd.find_repo")
    @patch("deep.storage.transaction.TransactionManager")
    @patch("deep.commands.gc_cmd.collect_garbage")
    def test_gc_default(self, mock_collect, mock_tm, mock_find):
        """Verify 'deep gc' with default arguments."""
        mock_find.return_value = self.repo_root
        mock_collect.return_value = (0, 100) # (collected, total)
        
        # Mock TransactionManager context manager
        mock_tm.return_value.__enter__.return_value = MagicMock()
        
        with patch("sys.stdout", new=StringIO()) as fake_out:
            main(["gc"])
            output = fake_out.getvalue()
            self.assertIn("⚓️ Garbage collection complete.", output)
            self.assertIn("No unreachable objects required pruning.", output)
            self.assertIn("100 objects remaining", output)
            
            # Verify collect_garbage call
            mock_collect.assert_called_once_with(
                self.repo_root, dry_run=False, verbose=False, prune_expire=3600
            )

    @patch("deep.commands.gc_cmd.find_repo")
    @patch("deep.storage.transaction.TransactionManager")
    @patch("deep.commands.gc_cmd.collect_garbage")
    def test_gc_dry_run(self, mock_collect, mock_tm, mock_find):
        """Verify 'deep gc --dry-run'."""
        mock_find.return_value = self.repo_root
        mock_collect.return_value = (5, 100) 
        
        mock_tm.return_value.__enter__.return_value = MagicMock()
        
        with patch("sys.stdout", new=StringIO()) as fake_out:
            main(["gc", "--dry-run"])
            output = fake_out.getvalue()
            self.assertIn("⚓️ Cleanup summary (dry-run):", output)
            self.assertIn("Unreachable objects that would be pruned: 5", output)
            self.assertIn("Run without --dry-run to relocate them", output)
            
            # Verify collect_garbage call
            mock_collect.assert_called_once_with(
                self.repo_root, dry_run=True, verbose=False, prune_expire=3600
            )

    @patch("deep.commands.gc_cmd.find_repo")
    @patch("deep.storage.transaction.TransactionManager")
    @patch("deep.commands.gc_cmd.collect_garbage")
    def test_gc_verbose_prune(self, mock_collect, mock_tm, mock_find):
        """Verify 'deep gc -v --prune 120'."""
        mock_find.return_value = self.repo_root
        mock_collect.return_value = (10, 100) 
        
        mock_tm.return_value.__enter__.return_value = MagicMock()
        
        with patch("sys.stdout", new=StringIO()) as fake_out:
            main(["gc", "-v", "--prune", "120"])
            output = fake_out.getvalue()
            self.assertIn("⚓️ Garbage collection complete.", output)
            self.assertIn("Relocated 10 unreachable objects", output)
            
            # Verify collect_garbage call
            mock_collect.assert_called_once_with(
                self.repo_root, dry_run=False, verbose=True, prune_expire=120
            )

    @patch("deep.commands.gc_cmd.find_repo")
    def test_gc_no_repo(self, mock_find):
        """Verify 'deep gc' fails gracefully outside a repository."""
        mock_find.side_effect = FileNotFoundError("Not a repository")
        
        with patch("sys.stdout", new=StringIO()) as fake_out:
            with self.assertRaises(DeepCLIException) as cm:
                main(["gc"])
            self.assertEqual(cm.exception.code, 1)
            output = fake_out.getvalue()
            self.assertIn("Deep: error: Not a repository", output)

if __name__ == "__main__":
    unittest.main()
