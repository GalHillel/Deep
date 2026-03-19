"""
tests.network.test_issue_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Unit tests for the GitHub issue command with mocking.
"""

import unittest
from unittest.mock import patch, MagicMock
import json
import io
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

    @patch("deep.commands.issue_cmd.api_request")
    @patch("deep.commands.issue_cmd.get_github_remote")
    @patch("deep.commands.issue_cmd.find_repo")
    def test_run_list_skips_prs(self, mock_find_repo, mock_get_remote, mock_api):
        mock_find_repo.return_value = self.repo_root
        mock_get_remote.return_value = "owner/repo"
        
        # Mock API returning an issue and a PR
        mock_api.return_value = [
            {"number": 1, "title": "Real Issue", "state": "open", "user": {"login": "alice"}},
            {"number": 2, "title": "Pull Request", "state": "open", "user": {"login": "bob"}, "pull_request": {}}
        ]
        
        self.args.issue_command = "list"
        
        with patch("sys.stdout", new=io.StringIO()) as fake_out:
            issue_cmd.run(self.args)
            output = fake_out.getvalue()
            
            self.assertIn("#1", output)
            self.assertIn("Real Issue", output)
            self.assertNotIn("#2", output)
            self.assertNotIn("Pull Request", output)

    @patch("deep.commands.issue_cmd.api_request")
    @patch("deep.commands.issue_cmd.get_github_remote")
    @patch("deep.commands.issue_cmd.find_repo")
    def test_run_show(self, mock_find_repo, mock_get_remote, mock_api):
        mock_find_repo.return_value = self.repo_root
        mock_get_remote.return_value = "owner/repo"
        mock_api.return_value = {
            "number": 123, "title": "Test Show", "state": "open", 
            "user": {"login": "alice"}, "html_url": "url", "body": "Hello world"
        }
        
        self.args.issue_command = "show"
        self.args.id = "123"
        
        with patch("sys.stdout", new=io.StringIO()) as fake_out:
            issue_cmd.run(self.args)
            output = fake_out.getvalue()
            self.assertIn("#123", output)
            self.assertIn("Test Show", output)
            self.assertIn("Hello world", output)

    @patch("deep.commands.issue_cmd.api_request")
    @patch("deep.commands.issue_cmd.get_github_remote")
    @patch("deep.commands.issue_cmd.find_repo")
    def test_run_create(self, mock_find_repo, mock_get_remote, mock_api):
        mock_find_repo.return_value = self.repo_root
        mock_get_remote.return_value = "owner/repo"
        mock_api.return_value = {"number": 1, "html_url": "url"}
        
        self.args.issue_command = "create"
        self.args.title = "New Issue"
        self.args.description = "Desc"
        
        issue_cmd.run(self.args)
        
        mock_api.assert_called_with("owner/repo/issues", method="POST", data={"title": "New Issue", "body": "Desc"}, verbose=False)

    @patch("deep.commands.issue_cmd.api_request")
    @patch("deep.commands.issue_cmd.get_github_remote")
    @patch("deep.commands.issue_cmd.find_repo")
    def test_run_close(self, mock_find_repo, mock_get_remote, mock_api):
        mock_find_repo.return_value = self.repo_root
        mock_get_remote.return_value = "owner/repo"
        
        self.args.issue_command = "close"
        self.args.id = "1"
        
        issue_cmd.run(self.args)
        
        mock_api.assert_called_with("owner/repo/issues/1", method="PATCH", data={"state": "closed"}, verbose=False)

if __name__ == "__main__":
    unittest.main()
