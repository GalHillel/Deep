import unittest
from unittest.mock import patch, MagicMock
import sys
from io import StringIO
from pathlib import Path
from deep.cli.main import main
from deep.core.errors import DeepCLIException

class TestFsckFlagsHealing(unittest.TestCase):
    def setUp(self):
        self.repo_root = Path("C:/fake/repo")
        self.dg_dir = self.repo_root / ".deep"
        self.fake_sha = "abc1234567890abcdef1234567890abcdef12345678" # 40 chars
        
    def test_fsck_help(self):
        """Verify 'deep fsck -h' contains expected flags."""
        with patch("sys.stdout", new=StringIO()) as fake_out:
            with self.assertRaises(SystemExit):
                main(["fsck", "-h"])
            output = fake_out.getvalue()
            self.assertIn("usage: deep fsck", output)
            self.assertIn("Perform a comprehensive repository consistency check", output)

    @patch("deep.core.repository.find_repo")
    @patch("deep.commands.fsck_cmd.Path.exists")
    @patch("deep.core.refs.list_branches")
    @patch("deep.core.refs.list_tags")
    @patch("deep.core.refs.resolve_head")
    @patch("deep.storage.objects.read_object")
    @patch("deep.commands.fsck_cmd.verify_object_integrity")
    def test_fsck_healthy(self, mock_verify, mock_read, mock_head, mock_tags, mock_branches, mock_exists, mock_find):
        """Verify 'deep fsck' reports healthy status for a clean repo."""
        mock_find.return_value = self.repo_root
        mock_exists.return_value = True
        mock_branches.return_value = []
        mock_tags.return_value = []
        mock_head.return_value = None
        mock_verify.return_value = True
        
        with patch("pathlib.Path.iterdir") as mock_p_iter:
            mock_p_iter.return_value = []
            
            with patch("sys.stdout", new=StringIO()) as fake_out:
                main(["fsck"])
                output = fake_out.getvalue()
                self.assertIn("⚓️ Fsck complete. Repository is healthy.", output)
                self.assertIn("Checked 0 objects, 0 corruption", output)

    @patch("deep.core.repository.find_repo")
    @patch("deep.commands.fsck_cmd.Path.exists")
    @patch("deep.core.refs.list_branches")
    @patch("deep.core.refs.list_tags")
    @patch("deep.core.refs.resolve_head")
    @patch("deep.core.refs.get_branch")
    @patch("deep.storage.objects.read_object")
    @patch("deep.commands.fsck_cmd.verify_object_integrity")
    def test_fsck_corrupt(self, mock_verify, mock_read, mock_get_branch, mock_head, mock_tags, mock_branches, mock_exists, mock_find):
        """Verify 'deep fsck' reports corruption when SHA-1 mismatch occurs."""
        mock_find.return_value = self.repo_root
        mock_exists.return_value = True
        mock_branches.return_value = ["main"]
        mock_tags.return_value = []
        mock_head.return_value = self.fake_sha
        mock_get_branch.return_value = self.fake_sha
        
        # Mock Path traversal
        mock_xx_dir = MagicMock()
        mock_xx_dir.is_dir.return_value = True
        mock_xx_dir.name = "de"
        
        mock_yy_file = MagicMock()
        mock_yy_file.name = "adbeefdeadbeefdeadbeefdeadbeefdeadbeef"
        
        mock_xx_dir.iterdir.return_value = [mock_yy_file]
        
        with patch("pathlib.Path.iterdir") as mock_p_iter:
            mock_p_iter.return_value = [mock_xx_dir] # For objects_dir.iterdir()
            
            mock_verify.return_value = False # Corruption!
            mock_read.side_effect = Exception("Missing")
            
            with patch("sys.stdout", new=StringIO()) as fake_out:
                main(["fsck"])
                output = fake_out.getvalue()
                self.assertIn("Found 1 corrupt objects!", output)
                self.assertIn("⚓️ Fsck complete. Repository has integrity ISSUES.", output)

    @patch("deep.core.repository.find_repo")
    @patch("deep.commands.fsck_cmd.Path.exists")
    @patch("deep.core.refs.list_branches")
    @patch("deep.core.refs.list_tags")
    @patch("deep.core.refs.resolve_head")
    @patch("deep.core.refs.get_branch")
    @patch("deep.storage.objects.read_object")
    @patch("deep.commands.fsck_cmd.verify_object_integrity")
    def test_fsck_dangling(self, mock_verify, mock_read, mock_get_branch, mock_head, mock_tags, mock_branches, mock_exists, mock_find):
        """Verify 'deep fsck' reports dangling objects not reachable from any ref."""
        mock_find.return_value = self.repo_root
        mock_exists.return_value = True
        mock_branches.return_value = []
        mock_tags.return_value = []
        mock_head.return_value = None
        mock_verify.return_value = True
        
        # 1 dangling object in the database
        dangling_sha = "00112233445566778899aabbccddeeff00112233"
        
        mock_xx_dir = MagicMock()
        mock_xx_dir.is_dir.return_value = True
        mock_xx_dir.name = "00"
        mock_yy_file = MagicMock()
        mock_yy_file.name = "112233445566778899aabbccddeeff00112233"
        
        # Ensure xx_dir.iterdir() works
        mock_xx_dir.iterdir.return_value = [mock_yy_file]
        
        with patch("pathlib.Path.iterdir") as mock_p_iter:
            mock_p_iter.return_value = [mock_xx_dir] # For objects_dir.iterdir()
            
            with patch("sys.stdout", new=StringIO()) as fake_out:
                main(["fsck"])
                output = fake_out.getvalue()
                self.assertIn("Found 1 dangling objects", output)
                self.assertIn("dangling: 00112233445566778899aabbccddeeff00112233", output)
                self.assertIn("⚓️ Fsck complete. Repository is healthy.", output)

if __name__ == "__main__":
    unittest.main()
