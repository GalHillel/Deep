import sys
import os
import time
from io import StringIO
from pathlib import Path
from unittest.mock import patch, MagicMock
from contextlib import ExitStack
import pytest
from deep.cli.main import main
from deep.core.errors import DeepCLIException

class TestMaintenanceFlagsHealing:
    @pytest.fixture(autouse=True)
    def setup_mocks(self, tmp_path):
        self.repo_root = tmp_path / "repo"
        self.repo_root.mkdir()
        self.dg_dir = self.repo_root / ".deep"
        self.dg_dir.mkdir()
        (self.dg_dir / "objects").mkdir()
        (self.dg_dir / "refs" / "heads").mkdir(parents=True)
        
        # Create a dummy HEAD
        (self.dg_dir / "HEAD").write_text("ref: refs/heads/main")

        with ExitStack() as stack:
            # Mock find_repo globally
            stack.enter_context(patch("deep.core.repository.find_repo", return_value=self.repo_root))
            stack.enter_context(patch("deep.commands.maintenance_cmd.find_repo", return_value=self.repo_root))
            
            # Mock core maintenance tasks to avoid real IO/Pack creation
            stack.enter_context(patch("deep.storage.commit_graph.build_history_graph"))
            stack.enter_context(patch("deep.core.maintenance.repack_repository"))
            
            self.mocks = stack
            yield
            
    def test_maintenance_help(self):
        """Verify 'deep maintenance -h' display."""
        with patch("sys.stdout", new=StringIO()) as fake_out:
            with pytest.raises(SystemExit):
                main(["maintenance", "-h"])
            output = fake_out.getvalue()
            assert "usage: deep maintenance" in output
            assert "--force" in output

    def test_maintenance_throttle_and_force(self):
        """Verify '--force' bypasses the 24h throttle."""
        from deep.core.maintenance import MAINTENANCE_LOG
        log_path = self.dg_dir / MAINTENANCE_LOG
        
        # 1. First run - should complete
        with patch("sys.stdout", new=StringIO()) as fake_out:
            main(["maintenance"])
            output = fake_out.getvalue()
            assert "Starting background maintenance..." in output
            assert "Maintenance complete." in output
            assert log_path.exists()
        
        # 2. Second run immediately - should be throttled (no output)
        with patch("sys.stdout", new=StringIO()) as fake_out:
            main(["maintenance"])
            output = fake_out.getvalue()
            assert "Starting background maintenance..." not in output
        
        # 3. Third run with --force - should bypass throttle
        with patch("sys.stdout", new=StringIO()) as fake_out:
            main(["maintenance", "--force"])
            output = fake_out.getvalue()
            assert "Starting background maintenance..." in output
            assert "Maintenance complete." in output

    def test_maintenance_non_repo_failure(self):
        """Verify 'deep maintenance' fails gracefully outside a repo."""
        # We need to override the fixture's mock for find_repo in the command module
        with patch("deep.commands.maintenance_cmd.find_repo", side_effect=FileNotFoundError("not a repository")):
            with patch("sys.stderr", new=StringIO()) as fake_err:
                with pytest.raises(DeepCLIException) as cm:
                    main(["maintenance"])
                assert cm.value.code == 1
                assert "error: not a repository" in fake_err.getvalue()

if __name__ == "__main__":
    import pytest
    pytest.main([__file__])
