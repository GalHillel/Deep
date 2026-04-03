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

class TestBenchmarkFlagsHealing:
    @pytest.fixture(autouse=True)
    def setup_repo(self, tmp_path):
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
            stack.enter_context(patch("deep.commands.benchmark_cmd.Path.cwd", return_value=self.repo_root))
            
            # Massive Scale Mocked Results
            self.mock_results = {
                "index_add_10k_time": 0.5,
                "index_add_10k_throughput": 20000.0,
                "commit_10k_tree_time": 1.0,
                "commit_10k_throughput": 10000.0,
                "status_scan_10k_time": 0.1,
                "status_detected": True,
                "log_1k_traversal_time": 0.05,
                "log_1k_count": 1000
            }
            stack.enter_context(patch("deep.commands.benchmark_cmd.run_benchmarks", return_value=self.mock_results))
            
            self.mocks = stack
            yield
            
    def test_benchmark_help(self):
        """Verify 'deep benchmark -h' display."""
        with patch("sys.stdout", new=StringIO()) as fake_out:
            with pytest.raises(SystemExit):
                main(["benchmark", "-h"])
            output = fake_out.getvalue()
            assert "usage: deep benchmark" in output
            assert "--report" in output

    def test_massive_benchmark_base_metrics(self):
        """Verify 'deep benchmark' massive scale reporting."""
        with patch("sys.stdout", new=StringIO()) as fake_out:
            main(["benchmark"])
            output = fake_out.getvalue()
            assert "⚓️ Initializing Massive Performance Engine..." in output
            assert "Deep Graphics Index Engine:" in output
            assert "Indexed 10,000 files" in output
            assert "Traversed 1,000 commits" in output

    def test_benchmark_report_generation(self, tmp_path):
        """Verify 'deep benchmark --report' exports JSON profile."""
        with patch("deep.commands.benchmark_cmd.Path", side_effect=lambda *args: (self.repo_root / args[0]) if args and isinstance(args[0], str) and "json" in args[0] else Path(*args)):
            with patch("sys.stdout", new=StringIO()) as fake_out:
                with patch("deep.commands.benchmark_cmd.open", create=True) as mock_open:
                    main(["benchmark", "--report"])
                    
                    # Verify open was called
                    mock_open.assert_called_once()
                    args, kwargs = mock_open.call_args
                    assert "benchmark_report.json" in str(args[0])

if __name__ == "__main__":
    import pytest
    pytest.main([__file__])
