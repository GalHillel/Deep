"""Tests for the embedded AI assistant (Phase 24)."""
from pathlib import Path
import subprocess, sys, os
import pytest

from deep.ai.assistant import DeepGitAI
from deep.ai.analyzer import (
    analyze_diff_text, classify_change, extract_keywords, score_complexity
)
from deep.core.repository import DEEP_GIT_DIR


@pytest.fixture
def ai_repo(tmp_path):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path.cwd())
    subprocess.run([sys.executable, "-m", "deep.main", "init"], cwd=tmp_path, env=env, check=True)
    (tmp_path / "main.py").write_text("def hello():\n    print('hi')\n")
    subprocess.run([sys.executable, "-m", "deep.main", "add", "main.py"], cwd=tmp_path, env=env, check=True)
    subprocess.run([sys.executable, "-m", "deep.main", "commit", "-m", "initial"], cwd=tmp_path, env=env, check=True)
    return tmp_path


# ── Analyzer Unit Tests ──
def test_analyze_diff_text():
    diff = "+hello\n-goodbye\n+world\n context\n"
    added, removed = analyze_diff_text(diff)
    assert added == 2
    assert removed == 1


def test_classify_change_docs():
    assert classify_change(["README.md"]) == "docs"


def test_classify_change_test():
    assert classify_change(["tests/test_foo.py"]) == "test"


def test_classify_change_feat():
    assert classify_change(["app.py", "utils.py"]) == "feat"


def test_extract_keywords():
    keywords = extract_keywords("def calculate_total(items):\n    total = sum(items)\n    return total")
    assert isinstance(keywords, list)
    assert len(keywords) > 0


def test_score_complexity():
    simple = "x = 1\n"
    complex_code = "\n".join([f"def func_{i}():\n    pass" for i in range(30)])
    assert score_complexity(simple) < score_complexity(complex_code)


# ── AI Assistant Integration Tests ──
def test_suggest_commit_message(ai_repo):
    (ai_repo / "main.py").write_text("def hello():\n    print('hello world')\n")
    ai = DeepGitAI(ai_repo)
    result = ai.suggest_commit_message()
    assert result.suggestion_type == "commit_msg"
    assert len(result.text) > 0
    assert result.confidence > 0
    assert result.latency_ms >= 0


def test_analyze_quality(ai_repo):
    ai = DeepGitAI(ai_repo)
    result = ai.analyze_quality()
    assert result.suggestion_type == "quality"
    assert len(result.text) > 0


def test_suggest_branch_name(ai_repo):
    ai = DeepGitAI(ai_repo)
    result = ai.suggest_branch_name("add user authentication")
    assert result.suggestion_type == "branch_name"
    assert "feature/" in result.text


def test_ai_metrics(ai_repo):
    ai = DeepGitAI(ai_repo)
    ai.suggest_commit_message()
    ai.analyze_quality()
    metrics = ai.get_metrics()
    assert metrics["suggestions_made"] == 2
    assert metrics["avg_latency_ms"] >= 0
