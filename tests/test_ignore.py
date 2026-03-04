"""
tests.test_ignore
~~~~~~~~~~~~~~~~~~
Tests for the .deepgitignore engine.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from deep_git.core.ignore import IgnoreEngine
from deep_git.main import main


@pytest.fixture()
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    main(["init"])
    return tmp_path


def test_ignore_engine_basic(repo: Path) -> None:
    (repo / ".deepgitignore").write_text("*.log\ntemp/\n!important.log\n")
    
    engine = IgnoreEngine(repo)
    
    # Wildcards
    assert engine.is_ignored("app.log") is True
    assert engine.is_ignored("nested/folder/app.log") is True
    
    # Directory match
    assert engine.is_ignored("temp", is_dir=True) is True
    assert engine.is_ignored("temp/file.txt") is True
    
    # Negation
    assert engine.is_ignored("important.log") is False
    assert engine.is_ignored("nested/important.log") is False
    
    # Normal files
    assert engine.is_ignored("main.py") is False


def test_add_recursive_with_ignore(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # Setup files and folders
    (repo / "src").mkdir()
    (repo / "src" / "main.py").write_text("code")
    (repo / "src" / "debug.log").write_text("log")
    (repo / ".deepgitignore").write_text("*.log\n")
    
    # Add from current dir
    main(["add", "."])
    
    # Status should show main.py added, but not debug.log
    capsys.readouterr()
    main(["status"])
    out = capsys.readouterr().out
    
    assert "new file:   src/main.py" in out
    assert "debug.log" not in out


def test_add_explicit_ignored_file(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (repo / "debug.log").write_text("log")
    (repo / ".deepgitignore").write_text("*.log\n")
    
    # Add specifically
    main(["add", "debug.log"])
    
    capsys.readouterr()
    main(["status"])
    out = capsys.readouterr().out
    
    # It should be added explicitly
    assert "new file:   debug.log" in out


def test_status_hides_ignored_files(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (repo / "debug.log").write_text("log")
    (repo / "normal.txt").write_text("txt")
    (repo / ".deepgitignore").write_text("*.log\n")
    
    main(["status"])
    out = capsys.readouterr().out
    
    assert "normal.txt" in out
    assert "debug.log" not in out
