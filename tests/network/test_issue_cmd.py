"""
tests.network.test_issue_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Unit tests for the GitHub issue command with mocking.
"""

import unittest
from unittest.mock import patch, MagicMock
import json
import io
import time
from pathlib import Path
from deep.commands import issue_cmd
from deep.core.issue import IssueManager, Issue
import deep.utils.network as net

class TestIssueCmd(unittest.TestCase):

    def setUp(self):
        self.repo_root = Path("/fake/repo")
        self.args = MagicMock()
        self.args.verbose = False
        self.args.id = None
        self.args.title = None
        self.args.description = None

    @patch("deep.utils.network.Config")
    def test_get_github_remote_https(self, mock_config):
        mock_instance = mock_config.return_value
        # Mock the raw config content since get_github_remote reads it directly
        with patch("pathlib.Path.read_text") as mock_read, patch("pathlib.Path.exists", return_value=True):
            mock_read.return_value = '[remote "origin"]\n  url = https://github.com/owner/repo.git'
            result = net.get_github_remote(self.repo_root)
            self.assertEqual(result, "owner/repo")

    @patch("deep.utils.network.Config")
    def test_get_github_remote_ssh(self, mock_config):
        with patch("pathlib.Path.read_text") as mock_read, patch("pathlib.Path.exists", return_value=True):
            mock_read.return_value = '[remote "origin"]\n  url = git@github.com:owner/repo.git'
            result = net.get_github_remote(self.repo_root)
            self.assertEqual(result, "owner/repo")

    @patch("os.environ.get")
    def test_get_token(self, mock_env_get):
        mock_env_get.side_effect = lambda k: "fake-token" if k in ["GH_TOKEN", "DEEP_TOKEN"] else None
        self.assertEqual(net.get_token(), "fake-token")

    @patch("urllib.request.urlopen")
    @patch("deep.utils.network.get_token")
    def test_api_request_success(self, mock_get_token, mock_urlopen):
        mock_get_token.return_value = "token123"
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = json.dumps({"foo": "bar"}).encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        result = net.api_request("test/path")
        self.assertEqual(result["foo"], "bar")
        
        # Verify headers
        args, kwargs = mock_urlopen.call_args
        req = args[0]
        self.assertEqual(req.get_header("Authorization"), "token token123")

    @patch("deep.utils.network.get_github_remote")
    @patch("deep.commands.issue_cmd.find_repo")
    def test_run_list(self, mock_find_repo, mock_get_remote):
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            mock_find_repo.return_value = tmp_path
            
            manager = IssueManager(tmp_path / ".deep")
            manager.create_issue("Local 1", "D1", "bug", "me")
            i2 = manager.create_issue("Local 2", "D2", "task", "me")
            manager.close_issue(i2.id)
            
            self.args.issue_command = "list"
            with patch("sys.stdout", new=io.StringIO()) as fake_out:
                issue_cmd.run(self.args)
                output = fake_out.getvalue()
                self.assertIn("#1", output)
                self.assertIn("Local 1", output)
                self.assertIn("#2", output)
                self.assertIn("CLOSED", output)

    @patch("deep.commands.issue_cmd.find_repo")
    def test_run_show(self, mock_find_repo):
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            mock_find_repo.return_value = tmp_path
            
            manager = IssueManager(tmp_path / ".deep")
            issue = manager.create_issue("Test Show", "Hello", "bug", "me")
            
            self.args.issue_command = "show"
            self.args.id = str(issue.id)
            
            with patch("sys.stdout", new=io.StringIO()) as fake_out:
                issue_cmd.run(self.args)
                output = fake_out.getvalue()
                self.assertIn(f"#{issue.id}", output)
                self.assertIn("Test Show", output)

    @patch("deep.commands.issue_cmd.find_repo")
    @patch("builtins.input", return_value="1") # Select 'bug'
    def test_run_create(self, mock_input, mock_find_repo):
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            mock_find_repo.return_value = tmp_path
            
            self.args.issue_command = "create"
            
            # Mock input for title, description etc
            with patch("builtins.input", side_effect=["1", "New Issue", "Step", "Exp", "Act", "n"]):
                issue_cmd.run(self.args)
            
            manager = IssueManager(tmp_path / ".deep")
            issues = manager.list_issues()
            self.assertEqual(len(issues), 1)
            self.assertEqual(issues[0].title, "New Issue")

    def test_local_manager_corruption(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            manager = IssueManager(tmp_path / ".deep")
            
            # Create a corrupt issue file
            corrupt_file = manager.issues_dir / "999.json"
            corrupt_file.write_text("{ invalid json")
                
            loaded = manager.list_issues()
            # New system silently ignores corrupt individual issues during list_issues
            self.assertEqual(len(loaded), 0)

    @patch("deep.utils.network.api_request")
    @patch("deep.utils.network.get_github_remote")
    @patch("deep.utils.network.get_token")
    @patch("deep.commands.issue_cmd.find_repo")
    @patch("builtins.input")
    def test_sync_during_create(self, mock_input, mock_find_repo, mock_get_token, mock_get_remote, mock_api):
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            mock_find_repo.return_value = tmp_path
            mock_get_token.return_value = "token123"
            mock_get_remote.return_value = "owner/repo"
            
            manager = IssueManager(tmp_path / ".deep")
            
            # Mock inputs for interactive_create
            # Selection: Feature (2), Title, Problem, Solution, Sync (y)
            mock_input.side_effect = ["2", "New Feat", "Prob", "Sol", "y"]
            
            mock_api.return_value = {"number": 456, "html_url": "http://gh/456"}
            
            # Call the internal helper that has sync logic
            issue = issue_cmd.interactive_create(manager, tmp_path)
            
            self.assertEqual(issue.title, "New Feat")
            self.assertEqual(issue.type, "feature")
            mock_api.assert_called_once()
            args, kwargs = mock_api.call_args
            self.assertEqual(kwargs["data"]["title"], "New Feat")

if __name__ == "__main__":
    unittest.main()

if __name__ == "__main__":
    unittest.main()
