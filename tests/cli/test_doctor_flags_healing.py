import unittest
from unittest.mock import patch, MagicMock
import sys
from io import StringIO
from pathlib import Path
import pytest
from contextlib import ExitStack
from deep.cli.main import main
from deep.core.errors import DeepCLIException

class TestDoctorFlagsHealing:
    @pytest.fixture(autouse=True)
    def setup_mocks(self, tmp_path):
        """Forensic mock management using ExitStack to prevent worker-level leaks."""
        self.repo_root = tmp_path / "repo"
        self.repo_root.mkdir()
        self.dg_dir = self.repo_root / ".deep"
        self.fake_sha = "abc1234567890abcdef1234567890abcdef12345678" # 40 chars
        
        with ExitStack() as stack:
            # 1. Path/Existence Mocks
            self.mock_exists = stack.enter_context(patch("deep.commands.doctor_cmd.Path.exists"))
            self.mock_mkdir = stack.enter_context(patch("pathlib.Path.mkdir"))
            self.mock_move = stack.enter_context(patch("shutil.move"))
            
            # 2. Repo/Ref Mocks (Targeting both command and core to prevent leakage)
            self.mock_find_repo = stack.enter_context(patch("deep.commands.doctor_cmd.find_repo"))
            self.mock_resolve_head = stack.enter_context(patch("deep.commands.doctor_cmd.resolve_head"))
            self.mock_list_branches = stack.enter_context(patch("deep.commands.doctor_cmd.list_branches"))
            self.mock_get_branch = stack.enter_context(patch("deep.commands.doctor_cmd.get_branch"))
            
            self.mock_core_find = stack.enter_context(patch("deep.core.repository.find_repo"))
            self.mock_core_resolve = stack.enter_context(patch("deep.core.refs.resolve_head"))
            self.mock_core_list = stack.enter_context(patch("deep.core.refs.list_branches"))
            
            # 3. Storage/Manager Mocks
            self.mock_read_index = stack.enter_context(patch("deep.commands.doctor_cmd.read_index"))
            self.mock_read_object = stack.enter_context(patch("deep.commands.doctor_cmd.read_object"))
            self.mock_pm_class = stack.enter_context(patch("deep.commands.doctor_cmd.PRManager"))
            self.mock_im_class = stack.enter_context(patch("deep.commands.doctor_cmd.IssueManager"))
            self.mock_reachable = stack.enter_context(patch("deep.commands.doctor_cmd.mark_reachable"))
            
            self.mock_storage_index = stack.enter_context(patch("deep.storage.index.read_index"))
            self.mock_walk = stack.enter_context(patch("deep.storage.objects.walk_loose_shas"))
            self.mock_read_safe = stack.enter_context(patch("deep.storage.objects.read_object_safe"))
            self.mock_obj_path = stack.enter_context(patch("deep.storage.objects._object_path"))

            # Initialize Defaults
            self.mock_exists.return_value = True
            self.mock_find_repo.return_value = self.repo_root
            self.mock_core_find.return_value = self.repo_root
            self.mock_resolve_head.return_value = self.fake_sha
            self.mock_core_resolve.return_value = self.fake_sha
            self.mock_list_branches.return_value = []
            self.mock_core_list.return_value = []
            self.mock_get_branch.return_value = self.fake_sha
            self.mock_reachable.return_value = set()
            self.mock_walk.return_value = []
            self.mock_read_safe.return_value = MagicMock()
            
            mock_idx = MagicMock(entries={})
            self.mock_read_index.return_value = mock_idx
            self.mock_storage_index.return_value = mock_idx
            
            self.mock_pm = self.mock_pm_class.return_value
            self.mock_pm.list_prs.return_value = []
            self.mock_im = self.mock_im_class.return_value
            self.mock_im.list_issues.return_value = []

            yield # All mocks are active during the test and cleared after

    def test_doctor_help(self):
        """Verify 'deep doctor -h' contains expected flags."""
        with patch("sys.stdout", new=StringIO()) as fake_out:
            with pytest.raises(SystemExit):
                main(["doctor", "-h"])
            output = fake_out.getvalue()
            assert "usage: deep doctor" in output
            assert "--fix" in output

    def test_doctor_healthy(self):
        """Verify 'deep doctor' reports healthy status for a clean repo."""
        with patch("sys.stdout", new=StringIO()) as fake_out:
            main(["doctor"])
            output = fake_out.getvalue()
            assert "⚓️ Repository consistent and healthy." in output

    def test_doctor_warnings(self):
        """Verify 'deep doctor' reports warnings for dangling objects."""
        # Mock 1 dangling object
        dangling_sha = "dangling1234567890abcdef1234567890abcdef12345678" # 40 chars
        self.mock_walk.return_value = [dangling_sha]
        
        with patch("sys.stdout", new=StringIO()) as fake_out:
            main(["doctor"])
            output = fake_out.getvalue()
            assert "Warning: 1 dangling objects found." in output
            assert "⚓️ Repository consistent, but 1 warnings found." in output

    def test_doctor_error(self):
        """Verify 'deep doctor' fails and exits 1 on object corruption."""
        self.mock_list_branches.return_value = ["main"]
        self.mock_core_list.return_value = ["main"]
        
        # Mock corruption in doctor_cmd.run
        with patch("deep.commands.doctor_cmd.read_object", side_effect=ValueError("Object missing")):
            with patch("sys.stdout", new=StringIO()) as fake_out:
                with pytest.raises(DeepCLIException) as cm:
                    main(["doctor"])
                assert cm.value.code == 1
                output = fake_out.getvalue()
                assert "⚓️ Integrity compromised." in output

    def test_doctor_fix(self):
        """Verify 'deep doctor --fix' triggers quarantine logic."""
        # Mock dangling object
        dangling_sha = "dangling1234567890abcdef1234567890abcdef1234"
        self.mock_walk.return_value = [dangling_sha]
        
        # Mock _object_path to return a path that exists
        mock_path_obj = MagicMock()
        mock_path_obj.exists.return_value = True
        self.mock_obj_path.return_value = mock_path_obj
        
        # Ensure mkdir/move don't fail
        self.mock_mkdir.return_value = None
        self.mock_move.return_value = None

        with patch("sys.stdout", new=StringIO()) as fake_out:
            main(["doctor", "--fix"])
            output = fake_out.getvalue()
            assert "Applying fixes..." in output
            assert f"Fixed: Quarantined dangling object {dangling_sha}" in output
            assert self.mock_move.called

if __name__ == "__main__":
    unittest.main()
