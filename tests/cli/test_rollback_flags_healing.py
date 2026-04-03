import sys
import os
import json
from io import StringIO
from pathlib import Path
from unittest.mock import patch, MagicMock
from contextlib import ExitStack
import pytest
from deep.cli.main import main
from deep.core.errors import DeepCLIException

class TestRollbackFlagsHealing:
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
            stack.enter_context(patch("deep.commands.rollback_cmd.find_repo", return_value=self.repo_root))
            
            self.mocks = stack
            yield
            
    def test_rollback_help(self):
        """Verify 'deep rollback -h' display."""
        with patch("sys.stdout", new=StringIO()) as fake_out:
            with pytest.raises(SystemExit):
                main(["rollback", "-h"])
            output = fake_out.getvalue()
            assert "usage: deep rollback" in output
            assert "--verify" in output

    def test_rollback_verify_audit(self):
        """Verify 'deep rollback --verify' triggers WAL audit."""
        # Create an empty WAL
        (self.dg_dir / "txlog").write_text("")
        
        with patch("sys.stdout", new=StringIO()) as fake_out:
            # We patch the core ref resolution
            with patch("deep.core.refs.resolve_head", return_value=None):
                main(["rollback", "--verify"])
            output = fake_out.getvalue()
            assert "⚓️ [WAL Security Check]" in output
            assert "✅ [WAL Security Check] All transaction signatures verified." in output

    def test_rollback_with_wal(self):
        """Verify 'deep rollback' uses WAL to find previous commit."""
        from deep.storage.txlog import TxRecord
        from deep.storage.objects import Commit
        
        # Set up two commits
        sha1 = "1111111111111111111111111111111111111111"
        sha2 = "2222222222222222222222222222222222222222"
        
        # Mock core functions
        with patch("deep.storage.objects.read_object") as mock_read:
            with patch("deep.core.refs.resolve_head", return_value=sha2):
                with patch("deep.commands.rollback_cmd._get_tree_files", return_value={}):
                    with patch("deep.storage.index.read_index") as mock_index:
                        mock_index.return_value.entries = {}
                        
                        # Mock the TransactionLog data
                        record_begin = TxRecord(tx_id="tx123", operation="commit", status="BEGIN", timestamp=1.0, 
                                               previous_commit_sha=sha1, branch_ref="refs/heads/main")
                        record_commit = TxRecord(tx_id="tx123", operation="", status="COMMIT", timestamp=1.1)
                        
                        txlog_path = self.dg_dir / "txlog"
                        txlog_path.write_text(json.dumps(record_begin.__dict__) + "\n" + json.dumps(record_commit.__dict__) + "\n")
                        
                        # Mock commit object for read_object
                        mock_commit = Commit(tree_sha="tree123", parent_shas=[sha1], author="me", timestamp=1.0, message="msg")
                        mock_read.return_value = mock_commit
                        
                        with patch("sys.stdout", new=StringIO()) as fake_out:
                            main(["rollback"])
                            output = fake_out.getvalue()
                            assert "⚓️ Rolling back transaction 'tx123'" in output
                            assert f"Restoring repository state to {sha1[:7]}" in output

    def test_rollback_explicit_commit(self):
        """Verify 'deep rollback <sha>' resets to specific commit."""
        sha_target = "abcde1234567890abcdef1234567890abcdef123"
        
        with patch("deep.core.refs.resolve_revision", return_value=sha_target):
            with patch("deep.storage.objects.read_object") as mock_read:
                with patch("deep.commands.rollback_cmd._get_tree_files", return_value={}):
                    with patch("deep.storage.index.read_index") as mock_index:
                        mock_index.return_value.entries = {}
                        
                        from deep.storage.objects import Commit
                        mock_commit = Commit(tree_sha="tree123", parent_shas=[], author="me", timestamp=1.0, message="msg")
                        mock_read.return_value = mock_commit
                        
                        with patch("sys.stdout", new=StringIO()) as fake_out:
                            main(["rollback", sha_target])
                            output = fake_out.getvalue()
                            assert f"Restoring repository state to {sha_target[:7]}" in output

if __name__ == "__main__":
    import pytest
    pytest.main([__file__])
