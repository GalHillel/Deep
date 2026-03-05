"""Tests for ultra AI features (Phase 34)."""
from pathlib import Path
import subprocess, sys, os
import pytest

from deep.ai.assistant import DeepGitAI
from deep.ai.analyzer import classify_change, extract_keywords, score_complexity
from deep.core.repository import DEEP_GIT_DIR


@pytest.fixture
def ultra_repo(tmp_path):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path.cwd())
    subprocess.run([sys.executable, "-m", "deep.main", "init"], cwd=tmp_path, env=env, check=True)
    # Create complex files
    engine_code = ""
    for i in range(5):
        engine_code += f"class Engine{i}:\n    def process(self): pass\n    def validate(self): pass\n\n"
    (tmp_path / "engine.py").write_text(engine_code)
    (tmp_path / "config.json").write_text('{"key": "value"}')
    subprocess.run([sys.executable, "-m", "deep.main", "add", "engine.py", "config.json"],
                   cwd=tmp_path, env=env, check=True)
    subprocess.run([sys.executable, "-m", "deep.main", "commit", "-m", "initial"],
                   cwd=tmp_path, env=env, check=True)
    return tmp_path


def test_refactoring_detection():
    """Classify diff with refactor keywords."""
    assert classify_change(["utils.py"], "refactor: extract helper method") == "refactor"


def test_conflict_prediction_hint(ultra_repo):
    ai = DeepGitAI(ultra_repo)
    hint = ai.merge_hint("feature-x", "main")
    assert hint.confidence > 0
    assert "Merge" in hint.text
    assert len(hint.details) >= 3


def test_file_clustering_suggestion(ultra_repo):
    """AI should handle multiple file types in staging."""
    ai = DeepGitAI(ultra_repo)
    result = ai.suggest_commit_message()
    assert len(result.text) > 0
    assert result.confidence > 0


def test_ai_metrics_tracking(ultra_repo):
    ai = DeepGitAI(ultra_repo)
    for _ in range(5):
        ai.suggest_commit_message()
    metrics = ai.get_metrics()
    assert metrics["suggestions_made"] == 5
    assert metrics["avg_latency_ms"] > 0


def test_branch_name_from_description():
    """Branch naming from description."""
    from deep.ai.assistant import DeepGitAI
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(Path.cwd())
        subprocess.run([sys.executable, "-m", "deep.main", "init"], cwd=tmp, env=env, check=True)
        ai = DeepGitAI(Path(tmp))
        result = ai.suggest_branch_name("fix login page authentication bug")
        assert "feature/" in result.text or "fix" in result.text.lower()
