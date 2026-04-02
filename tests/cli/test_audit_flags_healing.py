import unittest
from unittest.mock import patch, MagicMock
import sys
import time
import datetime
from io import StringIO
from pathlib import Path
from deep.cli.main import main
from deep.core.errors import DeepCLIException

class TestAuditFlagsHealing(unittest.TestCase):
    def setUp(self):
        self.repo_root = Path("C:/fake/repo")
        self.dg_dir = self.repo_root / ".deep"
        
    def test_audit_help(self):
        """Verify 'deep audit -h' contains expected positional arguments."""
        with patch("sys.stdout", new=StringIO()) as fake_out:
            with self.assertRaises(SystemExit):
                main(["audit", "-h"])
            output = fake_out.getvalue()
            self.assertIn("usage: deep audit", output)
            self.assertIn("{show,report,scan}", output)
            self.assertIn("⚓️ deep audit show", output)

    @patch("deep.core.repository.find_repo")
    @patch("deep.commands.audit_cmd.find_repo")
    @patch("deep.commands.audit_cmd.AuditLog")
    def test_audit_show_default(self, mock_audit, mock_find_cmd, mock_find_source):
        """Verify 'deep audit' (default show) displays entries in a table."""
        mock_find_cmd.return_value = self.repo_root
        mock_find_source.return_value = self.repo_root
        
        # Mock AuditEntry
        mock_entry = MagicMock()
        mock_entry.timestamp = time.time()
        mock_entry.user = "ghost"
        mock_entry.action = "commit"
        mock_entry.details = "Initial commit"
        
        mock_audit_instance = mock_audit.return_value
        mock_audit_instance.read_all.return_value = [mock_entry]
        
        with patch("sys.stdout", new=StringIO()) as fake_out:
            main(["audit"])
            output = fake_out.getvalue()
            self.assertIn("⚓️ RECENT SECURITY EVENTS", output)
            self.assertIn("ghost", output)
            self.assertIn("commit", output)
            self.assertIn("Initial commit", output)

    @patch("deep.core.repository.find_repo")
    @patch("deep.commands.audit_cmd.find_repo")
    @patch("deep.commands.audit_cmd.AuditLog")
    def test_audit_report(self, mock_audit, mock_find_cmd, mock_find_source):
        """Verify 'deep audit report' generates the security report."""
        mock_find_cmd.return_value = self.repo_root
        mock_find_source.return_value = self.repo_root
        
        mock_audit_instance = mock_audit.return_value
        mock_audit_instance.export_report.return_value = "DEEP AUDIT REPORT CONTENT"
        
        with patch("sys.stdout", new=StringIO()) as fake_out:
            main(["audit", "report"])
            output = fake_out.getvalue()
            self.assertIn("⚓️ Generating Comprehensive Security Audit Report...", output)
            self.assertIn("DEEP AUDIT REPORT CONTENT", output)

    @patch("deep.commands.audit_cmd._run_scan")
    def test_audit_scan_routing(self, mock_scan):
        """Verify 'deep audit scan' calls the scan utility."""
        with patch("sys.stdout", new=StringIO()):
            main(["audit", "scan"])
            self.assertTrue(mock_scan.called)

    @patch("deep.core.repository.find_repo")
    @patch("deep.commands.audit_cmd.find_repo")
    def test_audit_no_repo(self, mock_find_cmd, mock_find_source):
        """Verify 'deep audit show' fails gracefully outside a repository."""
        mock_find_cmd.side_effect = FileNotFoundError("Not a repository")
        mock_find_source.side_effect = FileNotFoundError("Not a repository")
        
        with patch("sys.stdout", new=StringIO()) as fake_out:
            with self.assertRaises(DeepCLIException) as cm:
                main(["audit", "show"])
            self.assertEqual(cm.exception.code, 1)
            output = fake_out.getvalue()
            self.assertIn("Deep: error: Not a repository", output)

if __name__ == "__main__":
    unittest.main()
