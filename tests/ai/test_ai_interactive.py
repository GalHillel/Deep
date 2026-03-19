"""
tests.test_ai_interactive
~~~~~~~~~~~~~~~~~~~~~~~~~
Tests for AI Commit Assistant features:
1. AI Commit Suggestions (--ai)
2. Change classification (Security/Perf)
3. Interactive query handling
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from deep.core.repository import DEEP_DIR
from deep.cli.main import main
from deep.ai.assistant import DeepAI

@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    os.chdir(repo)
    main(["init"])
    return repo

import builtins

def test_ai_commit_suggestion(repo: Path, monkeypatch):
    # Create a feature-like change
    f = repo / "auth.py"
    f.write_text("def login():\n    pass\n")
    main(["add", "auth.py"])
    
    # Mock user input to accept the AI suggestion
    monkeypatch.setattr(builtins, "input", lambda prompt="": "y")
    
    # Run commit with --ai
    main(["commit", "--ai"])
    
    # Verify commit exists and has a message
    from deep.core.refs import resolve_head
    from deep.storage.objects import read_object, Commit
    from deep.core.constants import DEEP_DIR # imported above
    
    sha = resolve_head(repo / DEEP_DIR)
    assert sha is not None
    commit = read_object(repo / DEEP_DIR / "objects", sha)
    assert isinstance(commit, Commit)
    assert "feat" in commit.message.lower() or "auth" in commit.message.lower()

def test_ai_classification_security(repo: Path):
    # Create a security-related change
    f = repo / "secrets.env"
    f.write_text("API_KEY=12345\n")
    main(["add", "secrets.env"])
    
    from deep.ai.assistant import DeepAI
    ai = DeepAI(repo)
    diff_text, stats = ai._get_staged_diff()
    
    from deep.ai.analyzer import classify_change
    cls = classify_change(["secrets.env"], diff_text)
    assert cls == "security"

def test_ai_classification_perf(repo: Path):
    # Create a performance-related change
    f = repo / "logic.py"
    f.write_text("def optimize_speed():\n    # faster implementation\n    pass\n")
    main(["add", "logic.py"])
    
    from deep.ai.assistant import DeepAI
    ai = DeepAI(repo)
    diff_text, stats = ai._get_staged_diff()
    
    from deep.ai.analyzer import classify_change
    cls = classify_change(["logic.py"], diff_text)
    assert cls == "perf"

def test_ai_handle_query(repo: Path):
    # Test fallback
    from deep.ai.assistant import DeepAI
    ai = DeepAI(repo)
    res = ai.handle_query("hello")
    assert "Ask me about your current changes" in res.text
    
    # Test security query
    f = repo / "passwords.txt"
    f.write_text("API_KEY_SECRET=mypassword\n")
    main(["add", "passwords.txt"])
    
    res = ai.handle_query("Are there any security issues?")
    # The refined analyzer or assistant should pick this up
    assert "security" in res.text.lower() or any("security" in d.lower() for d in res.details) or any("🔒" in d for d in res.details)
