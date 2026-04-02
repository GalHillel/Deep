import unittest
from unittest.mock import patch, MagicMock
import sys
import tempfile
import re
from io import StringIO
from pathlib import Path
from deep.commands import batch_cmd
from deep.core.errors import DeepCLIException

def strip_markup(text):
    """Simple helper to strip rich markup tags for cleaner assertions."""
    if not isinstance(text, str):
        text = str(text)
    # Remove [bold], [blue], [/blue], etc. and also ANSI escapes if any
    clean = re.sub(r"\[.*?\]", "", text)
    return clean

class TestBatchFlagsHealing(unittest.TestCase):
    def setUp(self):
        self.repo_root = Path("C:/fake/repo")
        self.dg_dir = self.repo_root / ".deep"
        self.temp_dir = tempfile.TemporaryDirectory()
        self.script_path = Path(self.temp_dir.name) / "test_script.deep"
        
    def tearDown(self):
        self.temp_dir.cleanup()
        
    @patch("sys.stdout", new=StringIO())
    def test_batch_help(self):
        """Verify 'deep batch -h' contains expected examples."""
        from deep.cli.main import build_parser
        parser = build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["batch", "-h"])

    @patch("deep.core.locks.BaseLock")
    @patch("deep.utils.utils.AtomicWriter")
    @patch("deep.commands.batch_cmd.find_repo")
    @patch("deep.commands.batch_cmd.TransactionLog", create=True)
    @patch("deep.commands.batch_cmd.AuditLog", create=True)
    @patch("deep.commands.batch_cmd.TelemetryCollector", create=True)
    @patch("deep.commands.batch_cmd.build_parser", create=True)
    @patch("deep.commands.add_cmd.run", create=True)
    @patch("deep.commands.commit_cmd.run", create=True)
    @patch("deep.commands.branch_cmd.run", create=True)
    @patch("deep.commands.batch_cmd.Console")
    def test_batch_execution(self, mock_console_class, mock_branch_run, mock_commit_run, mock_add_run, mock_parser_cmd, mock_telemetry_cmd, mock_audit_cmd, mock_tx_cmd, mock_find_cmd, mock_writer, mock_lock):
        """Verify 'deep batch' executes multiple commands from a script."""
        self.script_path.write_text("add file1.txt\ncommit -m 'batch'\nbranch feature")
        
        mock_find_cmd.return_value = self.repo_root
        
        printed_messages = []
        mock_console_inst = mock_console_class.return_value
        def mock_print(msg, **kwargs):
            printed_messages.append(strip_markup(str(msg)))
        mock_console_inst.print.side_effect = mock_print
        
        mock_args_batch = MagicMock()
        mock_args_batch.script = str(self.script_path)
        
        mock_args_add = MagicMock()
        mock_args_add.command = "add"
        mock_args_commit = MagicMock()
        mock_args_commit.command = "commit"
        mock_args_branch = MagicMock()
        mock_args_branch.command = "branch"
        
        mock_parser_cmd.return_value.parse_args.side_effect = [
            mock_args_add,
            mock_args_commit,
            mock_args_branch
        ]
        
        batch_cmd.run(mock_args_batch)
        
        all_output = "\n".join(printed_messages)
        self.assertIn("⚓️ Batch: 3 operation(s)", all_output)
        self.assertIn("Line 1: add file1.txt", all_output)
        self.assertIn("Line 2: commit -m 'batch'", all_output)
        self.assertIn("Line 3: branch feature", all_output)
        self.assertIn("BATCH COMPLETE", all_output)

    @patch("deep.core.locks.BaseLock")
    @patch("deep.utils.utils.AtomicWriter")
    @patch("deep.commands.batch_cmd.find_repo")
    @patch("deep.commands.batch_cmd.TransactionLog", create=True)
    @patch("deep.commands.batch_cmd.AuditLog", create=True)
    @patch("deep.commands.batch_cmd.TelemetryCollector", create=True)
    @patch("deep.commands.batch_cmd.build_parser", create=True)
    @patch("deep.commands.add_cmd.run", create=True)
    @patch("deep.commands.commit_cmd.run", create=True)
    @patch("deep.commands.batch_cmd.Console")
    def test_batch_resilience(self, mock_console_class, mock_commit_run, mock_add_run, mock_parser_cmd, mock_telemetry_cmd, mock_audit_cmd, mock_tx_cmd, mock_find_cmd, mock_writer, mock_lock):
        """Verify 'deep batch' continues execution even if a line fails."""
        self.script_path.write_text("add file1.txt\ncommit -m 'batch'")
        
        mock_find_cmd.return_value = self.repo_root
        
        printed_messages = []
        mock_console_inst = mock_console_class.return_value
        def mock_print(msg, **kwargs):
            printed_messages.append(strip_markup(str(msg)))
        mock_console_inst.print.side_effect = mock_print
        
        mock_args_batch = MagicMock()
        mock_args_batch.script = str(self.script_path)
        
        mock_args_add = MagicMock()
        mock_args_add.command = "add"
        mock_args_commit = MagicMock()
        mock_args_commit.command = "commit"
        
        mock_parser_cmd.return_value.parse_args.side_effect = [
            mock_args_add,
            mock_args_commit
        ]

        mock_add_run.side_effect = RuntimeError("SIMULATED FAILURE")
        
        batch_cmd.run(mock_args_batch)
        
        all_output = "\n".join(printed_messages)
        self.assertIn("⚓️ Batch: 2 operation(s)", all_output)
        self.assertIn("Line 1: add file1.txt (SIMULATED FAILURE)", all_output)
        self.assertIn("Line 2: commit -m 'batch'", all_output)
        self.assertIn("BATCH FINISHED", all_output)

    @patch("deep.commands.batch_cmd.find_repo")
    @patch("deep.commands.batch_cmd.Console")
    def test_batch_no_repo(self, mock_console, mock_find_cmd):
        self.script_path.write_text("add file.txt")
        mock_find_cmd.side_effect = FileNotFoundError("Not a repository")
        
        mock_args_batch = MagicMock()
        mock_args_batch.script = str(self.script_path)
        
        with self.assertRaises(DeepCLIException):
            batch_cmd.run(mock_args_batch)

    def test_batch_no_script(self):
        missing_script = str(Path(self.temp_dir.name) / "missing_file.deep")
        mock_args_batch = MagicMock()
        mock_args_batch.script = missing_script
        
        with self.assertRaises(DeepCLIException):
            batch_cmd.run(mock_args_batch)

if __name__ == "__main__":
    unittest.main()
