"""Tests for AI assistant advanced features (Phase 29)."""
from pathlib import Path
import subprocess, sys, os
import pytest

from deep.ai.assistant import DeepGitAI
from deep.ai.analyzer import score_complexity, extract_keywords, classify_change
from deep.core.repository import DEEP_DIR


@pytest.fixture
def advanced_repo(tmp_path):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path.cwd())
    subprocess.run([sys.executable, "-m", "deep.main", "init"], cwd=tmp_path, env=env, check=True)
    # Create multiple files
    (tmp_path / "app.py").write_text("def main():\n    print('app')\n")
    (tmp_path / "utils.py").write_text("def helper():\n    return 42\n")
    (tmp_path / "tests.py").write_text("def test_main():\n    assert True\n")
    subprocess.run([sys.executable, "-m", "deep.main", "add", "app.py", "utils.py", "tests.py"],
                   cwd=tmp_path, env=env, check=True)
    subprocess.run([sys.executable, "-m", "deep.main", "commit", "-m", "initial"],
                   cwd=tmp_path, env=env, check=True)
    return tmp_path


def test_predictive_commit_grouping(advanced_repo):
    """AI should handle commits with mixed file types."""
    (advanced_repo / "app.py").write_text("def main():\n    print('updated app')\n")
    (advanced_repo / "utils.py").write_text("def helper():\n    return 99\n")
    ai = DeepGitAI(advanced_repo)
    result = ai.suggest_commit_message()
    assert result.suggestion_type == "commit_msg"
    assert len(result.text) > 0


def test_merge_hint_quality(advanced_repo):
    ai = DeepGitAI(advanced_repo)
    result = ai.merge_hint("feature", "main")
    assert result.suggestion_type == "merge_hint"
    assert "feature" in result.text
    assert len(result.details) >= 3


def test_complexity_comparison():
    simple = "x = 1\ny = 2\n"
    medium = "\n".join([f"def func_{i}():\n    x = {i}\n    return x" for i in range(10)])
    complex_code = "\n".join([f"class C{i}:\n  def m{j}(self):\n    pass" for i in range(5) for j in range(5)])
    s1 = score_complexity(simple)
    s2 = score_complexity(medium)
    s3 = score_complexity(complex_code)
    assert s1 <= s2 <= s3


def test_keyword_extraction_consistency():
    diff = "def calculate_total(items):\n    total = sum(items)\n    return total"
    k1 = extract_keywords(diff)
    k2 = extract_keywords(diff)
    assert k1 == k2  # Deterministic


def test_change_classification_coverage():
    assert classify_change(["README.md"]) == "docs"
    assert classify_change(["test_foo.py"]) == "test"
    assert classify_change(["app.py"], "fix: resolve null pointer") == "fix"
    assert classify_change(["app.py"], "refactor: extract method") == "refactor"


def test_ai_concurrent_suggestions(advanced_repo):
    """Multiple suggestions should work without state corruption."""
    ai = DeepGitAI(advanced_repo)
    results = []
    for _ in range(10):
        results.append(ai.suggest_commit_message())
    assert all(r.suggestion_type == "commit_msg" for r in results)
    assert ai.get_metrics()["suggestions_made"] == 10
