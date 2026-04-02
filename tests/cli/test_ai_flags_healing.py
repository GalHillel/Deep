import unittest
from unittest.mock import patch, MagicMock
import sys
from io import StringIO
from pathlib import Path
from deep.cli.main import main
from deep.core.errors import DeepCLIException

class TestAIFlagsHealing(unittest.TestCase):
    def setUp(self):
        self.repo_root = Path("C:/fake/repo")
        self.deep_dir = self.repo_root / ".deep"
        
    def test_ai_help(self):
        """Verify 'deep ai -h' contains expected flags and subcommands."""
        with patch("sys.stdout", new=StringIO()) as fake_out:
            with self.assertRaises(SystemExit):
                main(["ai", "-h"])
            output = fake_out.getvalue()
            self.assertIn("usage: deep ai", output)
            self.assertIn("--description", output)
            self.assertIn("--source", output)
            self.assertIn("--branch", output)
            self.assertIn("suggest", output)
            self.assertIn("explain", output)
            self.assertIn("analyze", output)
            self.assertIn("review", output)

    @patch("deep.commands.ai_cmd.find_repo")
    @patch("deep.ai.assistant.DeepAI")
    def test_ai_suggest_success(self, mock_ai_class, mock_find_repo):
        """Verify 'deep ai suggest' works correctly."""
        mock_find_repo.return_value = self.repo_root
        mock_ai_inst = mock_ai_class.return_value
        
        mock_result = MagicMock()
        mock_result.text = "feat: add magic"
        mock_result.confidence = 0.95
        mock_result.latency_ms = 120.5
        mock_result.details = ["Analyzed 5 files"]
        mock_ai_inst.suggest_commit_message.return_value = mock_result
        
        with patch("sys.stdout", new=StringIO()) as fake_out:
            main(["ai", "suggest"])
            output = fake_out.getvalue()
            self.assertIn("💡 feat: add magic", output)
            self.assertIn("Confidence: 95%", output)
            self.assertIn("Analyzed 5 files", output)

    @patch("deep.commands.ai_cmd.find_repo")
    @patch("deep.ai.assistant.DeepAI")
    def test_ai_explain_success(self, mock_ai_class, mock_find_repo):
        """Verify 'deep ai explain' (newly added) works correctly."""
        mock_find_repo.return_value = self.repo_root
        mock_ai_inst = mock_ai_class.return_value
        
        mock_result = MagicMock()
        mock_result.text = "These changes optimize the object database."
        mock_result.details = ["Modified 2 files", "Removed 10 lines"]
        mock_ai_inst.analyze_quality.return_value = mock_result
        
        with patch("sys.stdout", new=StringIO()) as fake_out:
            main(["ai", "explain"])
            output = fake_out.getvalue()
            self.assertIn("📝 AI Explanation of changes:", output)
            self.assertIn("These changes optimize the object database.", output)
            self.assertIn("- Modified 2 files", output)

    @patch("deep.commands.ai_cmd.find_repo")
    @patch("deep.ai.assistant.DeepAI")
    def test_ai_generate_with_target_and_description(self, mock_ai_class, mock_find_repo):
        """Verify 'deep ai generate' correctly handles positional target and --description."""
        mock_find_repo.return_value = self.repo_root
        
        with patch("sys.stdout", new=StringIO()) as fake_out:
            # Command: deep ai generate "login logic" --description "use oauth2"
            main(["ai", "generate", "login logic", "--description", "use oauth2"])
            output = fake_out.getvalue()
            self.assertIn("💡 AI Suggestion for 'login logic use oauth2':", output)
            self.assertIn("implementation of the requested logic", output)

    @patch("deep.commands.ai_cmd.find_repo")
    @patch("deep.ai.assistant.DeepAI")
    def test_ai_predict_merge_flags(self, mock_ai_class, mock_find_repo):
        """Verify 'deep ai predict-merge' correctly resolves branches from flags."""
        mock_find_repo.return_value = self.repo_root
        mock_ai_inst = mock_ai_class.return_value
        
        mock_hint = MagicMock()
        mock_hint.text = "No conflicts"
        mock_hint.details = ["All clear"]
        mock_ai_inst.merge_hint.return_value = mock_hint
        
        with patch("sys.stdout", new=StringIO()) as fake_out:
            # deep ai predict-merge --source feature --branch main
            main(["ai", "predict-merge", "--source", "feature", "--branch", "main"])
            output = fake_out.getvalue()
            mock_ai_inst.merge_hint.assert_called_with("feature", "main")
            self.assertIn("🔮 No conflicts", output)

    @patch("deep.commands.ai_cmd.find_repo")
    @patch("deep.ai.assistant.DeepAI")
    def test_ai_assistant_alias(self, mock_ai_class, mock_find_repo):
        """Verify 'deep ai assistant' acts as an alias for interactive mode."""
        mock_find_repo.return_value = self.repo_root
        
        with patch("sys.stdin.isatty", return_value=False): # Force non-interactive exit
            with patch("sys.stdout", new=StringIO()) as fake_out:
                main(["ai", "assistant"])
                output = fake_out.getvalue()
                self.assertIn("🤖 Deep AI Assistant Mode", output)
                self.assertIn("[Non-interactive mode - exiting]", output)

    def test_ai_invalid_subcommand(self):
        """Verify unknown AI subcommands are caught by the parser."""
        with patch("sys.stderr", new=StringIO()):
            with self.assertRaises(SystemExit):
                main(["ai", "invalid-cmd"])

if __name__ == "__main__":
    unittest.main()
