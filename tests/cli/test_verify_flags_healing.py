import unittest
from unittest.mock import patch, MagicMock
import sys
from io import StringIO
from pathlib import Path
from deep.cli.main import main
from deep.core.errors import DeepCLIException

class TestVerifyFlagsHealing(unittest.TestCase):
    def setUp(self):
        self.repo_root = Path("C:/fake/repo")
        self.dg_dir = self.repo_root / ".deep"
        self.fake_sha = "abc1234567890abcdef1234567890abcdef12345678" # 40 chars
        
    def test_verify_help(self):
        """Verify 'deep verify -h' contains expected flags."""
        with patch("sys.stdout", new=StringIO()) as fake_out:
            with self.assertRaises(SystemExit):
                main(["verify", "-h"])
            output = fake_out.getvalue()
            self.assertIn("usage: deep verify", output)
            self.assertIn("--all", output)
            self.assertIn("--verbose", output)
            self.assertIn("⚓️ deep verify", output)

    @patch("deep.commands.verify_cmd.find_repo")
    @patch("deep.core.refs.resolve_head")
    @patch("deep.core.refs.list_branches")
    @patch("deep.core.refs.list_tags")
    @patch("deep.storage.objects.read_object_safe")
    @patch("deep.storage.objects.read_object")
    def test_verify_reachable_default(self, mock_read, mock_read_safe, mock_tags, mock_branches, mock_head, mock_find):
        """Verify 'deep verify' only checks reachable objects by default."""
        mock_find.return_value = self.repo_root
        mock_head.return_value = self.fake_sha
        mock_branches.return_value = []
        mock_tags.return_value = []
        
        # Mock Commit object
        mock_commit = MagicMock()
        mock_commit.tree_sha = "tree_sha_12345678901234567890123456789012"
        mock_commit.parent_shas = []
        mock_commit.signature = None
        
        mock_read.return_value = mock_commit
        mock_read_safe.return_value = mock_commit
        
        with patch("sys.stdout", new=StringIO()) as fake_out:
            main(["verify"])
            output = fake_out.getvalue()
            self.assertIn("VERIFICATION REPORT", output)
            self.assertIn("⚓️ Overall: ALL CHECKS PASSED", output)
            
            # Should have walked HEAD and its tree
            self.assertTrue(mock_read_safe.called)

    @patch("deep.commands.verify_cmd.find_repo")
    @patch("deep.storage.objects.walk_loose_shas")
    @patch("deep.storage.pack.PackReader.get_all_shas")
    @patch("deep.storage.objects.read_object_safe")
    def test_verify_all_objects(self, mock_read_safe, mock_pack_shas, mock_walk_loose, mock_find):
        """Verify 'deep verify --all' scans the entire database."""
        mock_find.return_value = self.repo_root
        
        loose_sha = "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"
        packed_sha = "cafebabecafebabecafebabecafebabecafebabe"
        
        mock_walk_loose.return_value = [loose_sha]
        mock_pack_shas.return_value = [packed_sha]
        
        # Mock object for read_safe
        mock_obj = MagicMock()
        mock_obj.signature = None
        mock_read_safe.return_value = mock_obj
        
        with patch("sys.stdout", new=StringIO()) as fake_out:
            main(["verify", "--all"])
            output = fake_out.getvalue()
            self.assertIn("Full database scan initiated", output)
            self.assertIn("Objects: 2 scanned", output) # 1 loose + 1 packed
            self.assertIn("⚓️ Overall: ALL CHECKS PASSED", output)
            
            # Verify read_safe was called for BOTH shas
            calls = [c[0][1] for c in mock_read_safe.call_args_list]
            self.assertIn(loose_sha, calls)
            self.assertIn(packed_sha, calls)

    @patch("deep.commands.verify_cmd.find_repo")
    @patch("deep.storage.objects.read_object_safe")
    def test_verify_verbose(self, mock_read_safe, mock_find):
        """Verify 'deep verify --verbose' prints progress."""
        mock_find.return_value = self.repo_root
        
        with patch("deep.core.refs.resolve_head", return_value=self.fake_sha), \
             patch("deep.core.refs.list_branches", return_value=[]), \
             patch("deep.core.refs.list_tags", return_value=[]), \
             patch("deep.storage.objects.read_object") as mock_read:
            
            mock_obj = MagicMock()
            mock_obj.tree_sha = "t" * 40
            mock_obj.parent_shas = []
            mock_obj.signature = None
            mock_read.return_value = mock_obj
            mock_read_safe.return_value = mock_obj
            
            with patch("sys.stdout", new=StringIO()) as fake_out:
                main(["verify", "--verbose"])
                output = fake_out.getvalue()
                self.assertIn(f"verify: {self.fake_sha}", output)

    @patch("deep.commands.verify_cmd.find_repo")
    @patch("deep.storage.objects.read_object_safe")
    def test_verify_corruption(self, mock_read_safe, mock_find):
        """Verify 'deep verify' reports issues and exits with code 2 on corruption."""
        mock_find.return_value = self.repo_root
        mock_read_safe.side_effect = ValueError("Hash mismatch!")
        
        # Force a walk that finds 1 object
        with patch("deep.core.refs.resolve_head", return_value=self.fake_sha), \
             patch("deep.core.refs.list_branches", return_value=[]), \
             patch("deep.core.refs.list_tags", return_value=[]), \
             patch("deep.storage.objects.read_object") as mock_read:
            
            mock_read.return_value = MagicMock() # commit walk succeeds, but verify fails
            
            with patch("sys.stdout", new=StringIO()) as fake_out:
                with self.assertRaises(DeepCLIException) as cm:
                    main(["verify"])
                self.assertEqual(cm.exception.code, 2)
                output = fake_out.getvalue()
                self.assertIn("⚓️ Overall: ISSUES DETECTED", output)
                self.assertIn("1 corruption(s)", output)

if __name__ == "__main__":
    unittest.main()
