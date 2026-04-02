import unittest
from unittest.mock import patch, MagicMock
import sys
from io import StringIO
from pathlib import Path
from deep.cli.main import main
from deep.core.errors import DeepCLIException

class TestDoctorFlagsHealing(unittest.TestCase):
    def setUp(self):
        self.repo_root = Path("C:/fake/repo")
        self.dg_dir = self.repo_root / ".deep"
        self.fake_sha = "abc1234567890abcdef1234567890abcdef12345678" # 40 chars
        
    def test_doctor_help(self):
        """Verify 'deep doctor -h' contains expected flags."""
        with patch("sys.stdout", new=StringIO()) as fake_out:
            with self.assertRaises(SystemExit):
                main(["doctor", "-h"])
            output = fake_out.getvalue()
            self.assertIn("usage: deep doctor", output)
            self.assertIn("--fix", output)

    @patch("deep.commands.doctor_cmd.Path.exists")
    @patch("deep.commands.doctor_cmd.find_repo")
    @patch("deep.commands.doctor_cmd.resolve_head")
    @patch("deep.commands.doctor_cmd.list_branches")
    @patch("deep.commands.doctor_cmd.get_branch")
    @patch("deep.commands.doctor_cmd.read_index")
    @patch("deep.commands.doctor_cmd.read_object")
    @patch("deep.commands.doctor_cmd.PRManager")
    @patch("deep.commands.doctor_cmd.IssueManager")
    @patch("deep.commands.doctor_cmd.mark_reachable")
    @patch("deep.core.repository.find_repo")
    @patch("deep.core.refs.resolve_head")
    @patch("deep.core.refs.list_branches")
    @patch("deep.storage.index.read_index")
    @patch("deep.storage.objects.walk_loose_shas")
    @patch("deep.storage.objects.read_object_safe")
    def test_doctor_healthy(self, mock_read_safe, mock_walk, mock_source_index, mock_source_list,
                           mock_source_head, mock_source_find, mock_reachable, mock_im_class,
                           mock_pm_class, mock_read_obj, mock_read_index, mock_get_branch,
                           mock_list_branches, mock_resolve_head, mock_find_repo, mock_exists):
        """Verify 'deep doctor' reports healthy status for a clean repo."""
        mock_exists.return_value = True
        mock_find_repo.return_value = self.repo_root
        mock_source_find.return_value = self.repo_root
        mock_list_branches.return_value = []
        mock_source_list.return_value = []
        mock_resolve_head.return_value = self.fake_sha
        mock_source_head.return_value = self.fake_sha
        mock_get_branch.return_value = self.fake_sha
        mock_reachable.return_value = set()
        mock_walk.return_value = []
        mock_read_safe.return_value = MagicMock()
        
        # Mock index
        mock_index = MagicMock()
        mock_index.entries = {}
        mock_read_index.return_value = mock_index
        mock_source_index.return_value = mock_index
        
        # Mock PRs/Issues
        mock_pm = mock_pm_class.return_value
        mock_pm.list_prs.return_value = []
        mock_im = mock_im_class.return_value
        mock_im.list_issues.return_value = []

        with patch("sys.stdout", new=StringIO()) as fake_out:
            main(["doctor"])
            output = fake_out.getvalue()
            self.assertIn("⚓️ Repository consistent and healthy.", output)

    @patch("deep.commands.doctor_cmd.Path.exists")
    @patch("deep.commands.doctor_cmd.find_repo")
    @patch("deep.commands.doctor_cmd.resolve_head")
    @patch("deep.commands.doctor_cmd.list_branches")
    @patch("deep.commands.doctor_cmd.get_branch")
    @patch("deep.commands.doctor_cmd.read_index")
    @patch("deep.commands.doctor_cmd.read_object")
    @patch("deep.commands.doctor_cmd.PRManager")
    @patch("deep.commands.doctor_cmd.IssueManager")
    @patch("deep.commands.doctor_cmd.mark_reachable")
    @patch("deep.core.repository.find_repo")
    @patch("deep.core.refs.resolve_head")
    @patch("deep.core.refs.list_branches")
    @patch("deep.storage.index.read_index")
    @patch("deep.storage.objects.walk_loose_shas")
    @patch("deep.storage.objects.read_object_safe")
    def test_doctor_warnings(self, mock_read_safe, mock_walk, mock_source_index, mock_source_list,
                             mock_source_head, mock_source_find, mock_reachable, mock_im_class,
                             mock_pm_class, mock_read_obj, mock_read_index, mock_get_branch,
                             mock_list_branches, mock_resolve_head, mock_find_repo, mock_exists):
        """Verify 'deep doctor' reports warnings for dangling objects."""
        mock_exists.return_value = True
        mock_find_repo.return_value = self.repo_root
        mock_source_find.return_value = self.repo_root
        mock_list_branches.return_value = []
        mock_source_list.return_value = []
        mock_resolve_head.return_value = self.fake_sha
        mock_source_head.return_value = self.fake_sha
        mock_get_branch.return_value = self.fake_sha
        mock_reachable.return_value = set()
        mock_read_safe.return_value = MagicMock()
        
        # Mock 1 dangling object
        dangling_sha = "dangling1234567890abcdef1234567890abcdef12345678" # 40 chars
        mock_walk.return_value = [dangling_sha]
        
        # Mock index/PR/Issue
        mock_idx = MagicMock(entries={})
        mock_read_index.return_value = mock_idx
        mock_source_index.return_value = mock_idx
        mock_pm_class.return_value.list_prs.return_value = []
        mock_im_class.return_value.list_issues.return_value = []

        with patch("sys.stdout", new=StringIO()) as fake_out:
            main(["doctor"])
            output = fake_out.getvalue()
            self.assertIn("Warning: 1 dangling objects found.", output)
            self.assertIn("⚓️ Repository consistent, but 1 warnings found.", output)

    @patch("deep.commands.doctor_cmd.Path.exists")
    @patch("deep.commands.doctor_cmd.find_repo")
    @patch("deep.commands.doctor_cmd.resolve_head")
    @patch("deep.commands.doctor_cmd.list_branches")
    @patch("deep.commands.doctor_cmd.get_branch")
    @patch("deep.commands.doctor_cmd.read_index")
    @patch("deep.commands.doctor_cmd.PRManager")
    @patch("deep.commands.doctor_cmd.IssueManager")
    @patch("deep.commands.doctor_cmd.mark_reachable")
    @patch("deep.core.repository.find_repo")
    @patch("deep.core.refs.resolve_head")
    @patch("deep.core.refs.list_branches")
    @patch("deep.storage.index.read_index")
    @patch("deep.storage.objects.walk_loose_shas")
    @patch("deep.storage.objects.read_object_safe")
    def test_doctor_error(self, mock_read_safe, mock_walk, mock_source_index, mock_source_list,
                          mock_source_head, mock_source_find, mock_reachable, mock_im_class,
                          mock_pm_class, mock_read_index, mock_get_branch, mock_list_branches,
                          mock_resolve_head, mock_find_repo, mock_exists):
        """Verify 'deep doctor' fails and exits 1 on object corruption."""
        mock_exists.return_value = True
        mock_find_repo.return_value = self.repo_root
        mock_source_find.return_value = self.repo_root
        mock_list_branches.return_value = ["main"]
        mock_source_list.return_value = ["main"]
        mock_resolve_head.return_value = self.fake_sha
        mock_source_head.return_value = self.fake_sha
        mock_get_branch.return_value = self.fake_sha
        mock_reachable.return_value = set()
        mock_walk.return_value = []
        mock_read_safe.return_value = MagicMock() # Make pre-check pass
        
        mock_idx = MagicMock(entries={})
        mock_read_index.return_value = mock_idx
        mock_source_index.return_value = mock_idx
        mock_pm_class.return_value.list_prs.return_value = []
        mock_im_class.return_value.list_issues.return_value = []
        
        # Mock corruption in doctor_cmd.run
        with patch("deep.commands.doctor_cmd.read_object", side_effect=ValueError("Object missing")):
            with patch("sys.stdout", new=StringIO()) as fake_out:
                with self.assertRaises(DeepCLIException) as cm:
                    main(["doctor"])
                self.assertEqual(cm.exception.code, 1)
                output = fake_out.getvalue()
                self.assertIn("⚓️ Integrity compromised.", output)

    @patch("deep.commands.doctor_cmd.Path.exists")
    @patch("deep.commands.doctor_cmd.find_repo")
    @patch("deep.commands.doctor_cmd.resolve_head")
    @patch("deep.commands.doctor_cmd.list_branches")
    @patch("deep.commands.doctor_cmd.get_branch")
    @patch("deep.commands.doctor_cmd.read_index")
    @patch("deep.commands.doctor_cmd.read_object")
    @patch("deep.commands.doctor_cmd.PRManager")
    @patch("deep.commands.doctor_cmd.IssueManager")
    @patch("deep.commands.doctor_cmd.mark_reachable")
    @patch("shutil.move")
    @patch("pathlib.Path.mkdir")
    @patch("deep.core.repository.find_repo")
    @patch("deep.core.refs.resolve_head")
    @patch("deep.core.refs.list_branches")
    @patch("deep.storage.index.read_index")
    @patch("deep.storage.objects.walk_loose_shas")
    @patch("deep.storage.objects.read_object_safe")
    @patch("deep.storage.objects._object_path")
    def test_doctor_fix(self, mock_obj_path, mock_read_safe, mock_walk, mock_source_index,
                        mock_source_list, mock_source_head, mock_source_find, mock_mkdir,
                        mock_move, mock_reachable, mock_im_class, mock_pm_class,
                        mock_read_obj, mock_read_index, mock_get_branch, mock_list_branches,
                        mock_resolve_head, mock_find_repo, mock_exists):
        """Verify 'deep doctor --fix' triggers quarantine logic."""
        mock_exists.return_value = True
        mock_find_repo.return_value = self.repo_root
        mock_source_find.return_value = self.repo_root
        mock_list_branches.return_value = []
        mock_source_list.return_value = []
        mock_resolve_head.return_value = self.fake_sha
        mock_source_head.return_value = self.fake_sha
        mock_get_branch.return_value = self.fake_sha
        mock_reachable.return_value = set()
        mock_read_safe.return_value = MagicMock()
        
        mock_idx = MagicMock(entries={})
        mock_read_index.return_value = mock_idx
        mock_source_index.return_value = mock_idx
        mock_pm_class.return_value.list_prs.return_value = []
        mock_im_class.return_value.list_issues.return_value = []
        
        # Mock dangling object
        dangling_sha = "dangling1234567890abcdef1234567890abcdef1234"
        mock_walk.return_value = [dangling_sha]
        
        # Mock _object_path to return a path that exists
        mock_path_obj = MagicMock()
        mock_path_obj.exists.return_value = True
        mock_obj_path.return_value = mock_path_obj
        
        # Ensure mkdir/move don't fail
        mock_mkdir.return_value = None
        mock_move.return_value = None

        with patch("sys.stdout", new=StringIO()) as fake_out:
            main(["doctor", "--fix"])
            output = fake_out.getvalue()
            self.assertIn("Applying fixes...", output)
            self.assertIn(f"Fixed: Quarantined dangling object {dangling_sha}", output)
            self.assertTrue(mock_move.called)

if __name__ == "__main__":
    unittest.main()
