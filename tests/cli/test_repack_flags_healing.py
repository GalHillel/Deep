import unittest
from unittest.mock import patch, MagicMock
import sys
from io import StringIO
from pathlib import Path
from deep.cli.main import main
from deep.core.errors import DeepCLIException

class TestRepackFlagsHealing(unittest.TestCase):
    def setUp(self):
        self.repo_root = Path("C:/fake/repo")
        self.dg_dir = self.repo_root / ".deep"
        
    def test_repack_help(self):
        """Verify 'deep repack -h' contains expected flags."""
        with patch("sys.stdout", new=StringIO()) as fake_out:
            with self.assertRaises(SystemExit):
                main(["repack", "-h"])
            output = fake_out.getvalue()
            self.assertIn("usage: deep repack", output)
            self.assertIn("--no-bitmaps", output)
            self.assertIn("⚓️ deep repack", output)

    @patch("deep.core.repository.find_repo")
    @patch("deep.storage.transaction.TransactionManager")
    @patch("deep.storage.pack.PackWriter")
    @patch("deep.storage.bitmap.generate_pack_bitmaps")
    @patch("deep.core.refs.resolve_head")
    @patch("deep.storage.objects.get_reachable_objects")
    def test_repack_default(self, mock_reachable, mock_head, mock_bm, mock_pw, mock_tm, mock_find):
        """Verify 'deep repack' generates bitmaps by default."""
        mock_find.return_value = self.repo_root
        mock_head.return_value = "abc1234567890abcdef1234567890abcdef12345678"
        mock_reachable.return_value = ["sha1", "sha2"]
        
        # Mock PackWriter
        mock_pw_instance = mock_pw.return_value
        mock_pw_instance.create_pack.return_value = ("pack_sha", "idx_sha")
        
        # Mock TransactionManager context manager
        mock_tm.return_value.__enter__.return_value = MagicMock()
        
        with patch("sys.stdout", new=StringIO()) as fake_out:
            # We mock the other refs to be empty
            with patch("deep.core.refs.list_branches", return_value=[]), \
                 patch("deep.core.refs.list_tags", return_value=[]):
                main(["repack"])
                output = fake_out.getvalue()
                self.assertIn("⚓️ Repacking repository objects...", output)
                self.assertIn("Found 2 reachable objects.", output)
                self.assertIn("⚓️ Created pack-pack_sha.pack", output)
                self.assertIn("⚓️ Generating reachability bitmaps...", output)
                self.assertTrue(mock_bm.called)
                self.assertIn("⚓️ Repack complete", output)

    @patch("deep.core.repository.find_repo")
    @patch("deep.storage.transaction.TransactionManager")
    @patch("deep.storage.pack.PackWriter")
    @patch("deep.storage.bitmap.generate_pack_bitmaps")
    @patch("deep.core.refs.resolve_head")
    @patch("deep.storage.objects.get_reachable_objects")
    def test_repack_no_bitmaps(self, mock_reachable, mock_head, mock_bm, mock_pw, mock_tm, mock_find):
        """Verify 'deep repack --no-bitmaps' disables bitmap generation."""
        mock_find.return_value = self.repo_root
        mock_head.return_value = "abc1234567890abcdef1234567890abcdef12345678"
        mock_reachable.return_value = ["sha1"]
        
        mock_pw_instance = mock_pw.return_value
        mock_pw_instance.create_pack.return_value = ("pack_sha", "idx_sha")
        
        mock_tm.return_value.__enter__.return_value = MagicMock()
        
        with patch("sys.stdout", new=StringIO()) as fake_out:
            with patch("deep.core.refs.list_branches", return_value=[]), \
                 patch("deep.core.refs.list_tags", return_value=[]):
                main(["repack", "--no-bitmaps"])
                output = fake_out.getvalue()
                self.assertIn("⚓️ Bitmap generation disabled by user flag.", output)
                self.assertFalse(mock_bm.called)
                self.assertIn("⚓️ Repack complete", output)

    @patch("deep.core.repository.find_repo")
    @patch("deep.storage.transaction.TransactionManager")
    @patch("deep.core.refs.resolve_head")
    def test_repack_no_heads(self, mock_head, mock_tm, mock_find):
        """Verify 'deep repack' when there is nothing to repack."""
        mock_find.return_value = self.repo_root
        mock_head.return_value = None
        
        mock_tm.return_value.__enter__.return_value = MagicMock()
        
        with patch("sys.stdout", new=StringIO()) as fake_out:
            with patch("deep.core.refs.list_branches", return_value=[]), \
                 patch("deep.core.refs.list_tags", return_value=[]):
                main(["repack"])
                output = fake_out.getvalue()
                self.assertIn("⚓️ Nothing to repack (no commits found).", output)

    @patch("deep.core.repository.find_repo")
    def test_repack_no_repo(self, mock_find):
        """Verify 'deep repack' fails gracefully outside a repository."""
        mock_find.side_effect = FileNotFoundError("Not a repository")
        
        with patch("sys.stdout", new=StringIO()) as fake_out:
            with self.assertRaises(DeepCLIException) as cm:
                main(["repack"])
            self.assertEqual(cm.exception.code, 1)
            output = fake_out.getvalue()
            self.assertIn("Deep: error: Not a repository", output)

if __name__ == "__main__":
    unittest.main()
