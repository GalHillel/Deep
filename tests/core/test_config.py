"""
tests.test_config
~~~~~~~~~~~~~~~~~~
Tests for the configuration system (`.deepconfig` / `.deep/config`).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from deep.core.config import Config
from deep.cli.main import main


@pytest.fixture()
def repo_with_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    
    # Fake a home directory for global config isolation
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    
    monkeypatch.chdir(repo_path)
    main(["init"])
    return repo_path


def test_config_global_and_local(repo_with_home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # Set global value
    main(["config", "--global", "user.name", "Global User"])
    
    # Check it passes through to get
    capsys.readouterr()
    main(["config", "user.name"])
    out = capsys.readouterr().out.strip()
    assert out == "Global User"
    
    # Set local override
    main(["config", "user.name", "Local User"])
    main(["config", "user.name"])
    out = capsys.readouterr().out.strip()
    assert out == "Local User"
    
    # Global is untouched
    main(["config", "--global", "user.name"])
    out = capsys.readouterr().out.strip()
    assert out == "Global User"


def test_commit_uses_config(repo_with_home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    main(["config", "user.name", "Alice"])
    main(["config", "user.email", "alice@wonder.land"])
    
    (repo_with_home / "f.txt").write_text("v1")
    main(["add", "f.txt"])
    main(["commit", "-m", "msg"])
    
    capsys.readouterr()
    main(["log"])
    out = capsys.readouterr().out
    
    assert "Author: Alice <alice@wonder.land>" in out


def test_missing_config_fallback(repo_with_home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # Exits 1 if not found
    with pytest.raises(SystemExit) as excinfo:
        main(["config", "does.notexist"])
    assert excinfo.value.code == 1

def test_config_outside_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    monkeypatch.chdir(tmp_path)  # NOT a repo
    
    # Global set works
    main(["config", "--global", "user.name", "Out Repo"])
    capsys.readouterr()
    main(["config", "--global", "user.name"])
    out = capsys.readouterr().out.strip()
    assert out == "Out Repo"
    
    # Local get/set fails outside repo
    with pytest.raises(SystemExit) as excinfo:
        main(["config", "user.name"])
    assert excinfo.value.code == 1
