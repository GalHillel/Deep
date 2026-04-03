import sys
import os
import shutil
from io import StringIO
from pathlib import Path
from unittest.mock import patch, MagicMock
from contextlib import ExitStack
import pytest
from deep.cli.main import main
from deep.core.errors import DeepCLIException
from deep.core.config import set_config
from deep.storage.objects import Blob, Commit, Tree, TreeEntry

class TestMigrateFlagsHealing:
    @pytest.fixture(autouse=True)
    def setup_v1_repo(self, tmp_path):
        """Build a legacy v1 repository."""
        self.repo_root = tmp_path / "repo_v1"
        self.repo_root.mkdir()
        self.dg_dir = self.repo_root / ".deep"
        self.dg_dir.mkdir()
        (self.dg_dir / "objects").mkdir()
        (self.dg_dir / "refs" / "heads").mkdir(parents=True)
        
        # 1. Config v1
        set_config(self.dg_dir, {"format_version": 1, "user.name": "V1 User"})
        
        # 2. Loose Objects
        objects_dir = self.dg_dir / "objects"
        b_sha = Blob(data=b"v1 content").write(objects_dir)
        t = Tree(entries=[TreeEntry(mode="100644", name="f.txt", sha=b_sha)])
        t_sha = t.write(objects_dir)
        c = Commit(tree_sha=t_sha, message="v1 commit")
        c_sha = c.write(objects_dir)
        
        # 3. HEAD and Index
        (self.dg_dir / "HEAD").write_text(c_sha)
        (self.dg_dir / "index").write_text("DPIX" + "\x00" * 12) # Dummy v1 index header

        with ExitStack() as stack:
            # Mock find_repo globally to target our v1 repo
            stack.enter_context(patch("deep.core.repository.find_repo", return_value=self.repo_root))
            stack.enter_context(patch("deep.commands.migrate_cmd.find_repo", return_value=self.repo_root))
            
            self.mocks = stack
            yield
            
    def test_migrate_help(self):
        """Verify 'deep migrate -h' display."""
        with patch("sys.stdout", new=StringIO()) as fake_out:
            with pytest.raises(SystemExit):
                main(["migrate", "-h"])
            output = fake_out.getvalue()
            assert "usage: deep migrate" in output
            assert "Repacks history and converts metadata" in output

    def test_migrate_v1_to_v2_success(self):
        """Verify 'deep migrate' correctly upgrades format and repacks objects."""
        with patch("sys.stdout", new=StringIO()) as fake_out:
            # Run migration
            main(["migrate"])
            output = fake_out.getvalue()
            
            assert "Migrating repository" in output
            assert "Repacking objects into DeepVault..." in output
            assert "Building DeepHistoryGraph..." in output
            assert "Migration complete" in output

            # Verification of results
            from deep.core.config import get_config
            config = get_config(self.dg_dir)
            assert int(config["format_version"]) == 2
            
            # Check for vault directory
            vault_dir = self.dg_dir / "objects" / "vault"
            assert vault_dir.exists()
            assert any(vault_dir.glob("*.dvpf"))
            
            # Check for commit-graph (DHGX)
            cg_file = self.dg_dir / "objects" / "info" / "history-graph"
            assert cg_file.exists()

    def test_migrate_already_v2(self):
        """Verify 'deep migrate' handles already-upgraded repos gracefully."""
        # Force v2
        set_config(self.dg_dir, {"format_version": 2})
        
        with patch("sys.stdout", new=StringIO()) as fake_out:
            main(["migrate"])
            output = fake_out.getvalue()
            assert "already at version 2. No migration needed." in output

if __name__ == "__main__":
    import pytest
    pytest.main([__file__])
