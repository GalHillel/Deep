"""Tests for AI-assisted code review (Phase 43)."""
from pathlib import Path
import subprocess, sys, os, json
import pytest

from deep.core.repository import DEEP_DIR


@pytest.fixture
def ai_review_repo(tmp_path):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path.cwd())
    subprocess.run([sys.executable, "-m", "deep.main", "init"], cwd=tmp_path, env=env, check=True)
    
    # Create an initial commit
    (tmp_path / "main.py").write_text("print('hello')")
    subprocess.run([sys.executable, "-m", "deep.main", "add", "main.py"], cwd=tmp_path, env=env, check=True)
    subprocess.run([sys.executable, "-m", "deep.main", "commit", "-m", "initial"], cwd=tmp_path, env=env, check=True)
    
    return tmp_path, env


def test_ai_review_findings(ai_review_repo):
    repo, env = ai_review_repo
    # Add a TODO and a secret
    (repo / "main.py").write_text("print('hello')\n# TODO: fix this\nAPI_KEY = 'secret'")
    subprocess.run([sys.executable, "-m", "deep.main", "add", "main.py"], cwd=repo, env=env, check=True)
    
    result = subprocess.run(
        [sys.executable, "-m", "deep.main", "ai", "review"],
        cwd=repo, env=env, capture_output=True, text=True, check=True
    )
    assert "TODO found" in result.stdout
    assert "Sensitive keyword" in result.stdout


def test_ai_review_clean(ai_review_repo):
    repo, env = ai_review_repo
    # No changes
    result = subprocess.run(
        [sys.executable, "-m", "deep.main", "ai", "review"],
        cwd=repo, env=env, capture_output=True, text=True, check=True
    )
    assert "No critical issues found" in result.stdout


def test_ai_predict_merge_cli(ai_review_repo):
    repo, env = ai_review_repo
    result = subprocess.run(
        [sys.executable, "-m", "deep.main", "ai", "predict-merge"],
        cwd=repo, env=env, capture_output=True, text=True, check=True
    )
    assert "Prediction:" in result.stdout


def test_ai_review_api(ai_review_repo):
    from deep.ai.assistant import DeepGitAI
    repo, env = ai_review_repo
    # Add a TODO
    (repo / "main.py").write_text("print('hello')\n# TODO: wait")
    subprocess.run([sys.executable, "-m", "deep.main", "add", "main.py"], cwd=repo, env=env, check=True)

    ai = DeepGitAI(repo)
    res = ai.review_changes()
    assert any("TODO" in d for d in res.details)
