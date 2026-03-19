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

class TestIssueCmd(unittest.TestCase):

    def setUp(self):
        self.repo_root = Path("/fake/repo")
        self.args = MagicMock()
        self.args.verbose = False
        self.args.id = None
        self.args.title = None
        self.args.description = None

    @patch("deep.commands.issue_cmd.Config")
    def test_get_github_remote_https(self, mock_config):
        mock_instance = mock_config.return_value
        mock_instance.get.return_value = "https://github.com/owner/repo.git"
        
        result = issue_cmd.get_github_remote(self.repo_root)
        self.assertEqual(result, "owner/repo")

    @patch("deep.commands.issue_cmd.Config")
    def test_get_github_remote_ssh(self, mock_config):
        mock_instance = mock_config.return_value
        mock_instance.get.return_value = "git@github.com:owner/repo.git"
        
        result = issue_cmd.get_github_remote(self.repo_root)
        self.assertEqual(result, "owner/repo")

    @patch("os.environ.get")
    def test_get_token(self, mock_env_get):
        mock_env_get.side_effect = lambda k: "fake-token" if k == "GH_TOKEN" else None
        self.assertEqual(issue_cmd.get_token(), "fake-token")

    @patch("urllib.request.urlopen")
    @patch("deep.commands.issue_cmd.get_token")
    def test_api_request_success(self, mock_get_token, mock_urlopen):
        mock_get_token.return_value = "token123"
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = json.dumps({"foo": "bar"}).encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        result = issue_cmd.api_request("test/path")
        self.assertEqual(result, {"foo": "bar"})
        
        # Verify headers
        args, kwargs = mock_urlopen.call_args
        req = args[0]
        self.assertEqual(req.get_header("Authorization"), "token token123")

    @patch("deep.commands.issue_cmd.get_github_remote")
    @patch("deep.commands.issue_cmd.find_repo")
    def test_run_list(self, mock_find_repo, mock_get_remote):
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            mock_find_repo.return_value = tmp_path
            
            manager = issue_cmd.LocalIssueManager(tmp_path)
            issues = [
                {"id": 1, "title": "Local 1", "state": "open", "created_at": time.time()},
                {"id": 2, "title": "Local 2", "state": "closed", "created_at": time.time()}
            ]
            manager.save_all(issues)
            
            self.args.issue_command = "list"
            with patch("sys.stdout", new=io.StringIO()) as fake_out:
                issue_cmd.run(self.args)
                output = fake_out.getvalue()
                self.assertIn("#1", output)
                self.assertIn("Local 1", output)
                self.assertIn("#2", output)
                self.assertIn("[CLOSED]", output)

    @patch("deep.commands.issue_cmd.find_repo")
    def test_run_show(self, mock_find_repo):
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            mock_find_repo.return_value = tmp_path
            
            manager = issue_cmd.LocalIssueManager(tmp_path)
            issue = {"id": 123, "title": "Test Show", "state": "open", "created_at": time.time(), "body": "Hello"}
            manager.save_all([issue])
            
            self.args.issue_command = "show"
            self.args.id = "123"
            
            with patch("sys.stdout", new=io.StringIO()) as fake_out:
                issue_cmd.run(self.args)
                output = fake_out.getvalue()
                self.assertIn("#123", output)
                self.assertIn("Test Show", output)

    @patch("deep.commands.issue_cmd.find_repo")
    def test_run_create(self, mock_find_repo):
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            mock_find_repo.return_value = tmp_path
            
            self.args.issue_command = "create"
            self.args.title = "New Issue"
            self.args.description = "Desc"
            
            issue_cmd.run(self.args)
            
            manager = issue_cmd.LocalIssueManager(tmp_path)
            issues = manager.load_all()
            self.assertEqual(len(issues), 1)
            self.assertEqual(issues[0]["title"], "New Issue")

    @patch("deep.commands.issue_cmd.shutil.copy")
    def test_local_manager_corruption(self, mock_copy):
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            manager = issue_cmd.LocalIssueManager(tmp_path)
            manager.dg_dir.mkdir(parents=True, exist_ok=True)
            
            with open(manager.issue_file, "w") as f:
                f.write("{ invalid json")
                
            loaded = manager.load_all()
            self.assertEqual(loaded, [])
            mock_copy.assert_called()

    @patch("deep.commands.issue_cmd.api_request")
    @patch("deep.commands.issue_cmd.get_github_remote")
    @patch("deep.commands.issue_cmd.get_token")
    @patch("deep.commands.issue_cmd.find_repo")
    def test_run_sync(self, mock_find_repo, mock_get_token, mock_get_remote, mock_api):
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            mock_find_repo.return_value = tmp_path
            mock_get_token.return_value = "token123"
            mock_get_remote.return_value = "owner/repo"
            
            manager = issue_cmd.LocalIssueManager(tmp_path)
            issue = {"id": 1, "title": "Local", "body": "B", "state": "open", "github_id": None}
            manager.save_all([issue])
            
            mock_api.return_value = {"number": 456}
            self.args.issue_command = "sync"
            issue_cmd.run(self.args)
            
            updated_issues = manager.load_all()
            self.assertEqual(updated_issues[0]["github_id"], 456)

if __name__ == "__main__":
    unittest.main()
