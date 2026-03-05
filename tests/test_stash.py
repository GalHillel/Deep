"""
tests.test_stash
~~~~~~~~~~~~~~~~
Tests for the stash engine (save, list, pop).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from deep.core.repository import DEEP_GIT_DIR
from deep.cli.main import main


@pytest.fixture()
def repo_with_commit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    main(["init"])
    
    # Create base file
    f = tmp_path / "f.txt"
    f.write_text("v1")
    main(["add", "f.txt"])
    main(["commit", "-m", "base commit"])
    return tmp_path


def test_stash_save_and_list(repo_with_commit: Path, capsys: pytest.CaptureFixture[str]) -> None:
    f = repo_with_commit / "f.txt"
    f.write_text("v2")
    
    # Stash save
    capsys.readouterr()
    main(["stash", "save"])
    out = capsys.readouterr().out
    assert "Saved working directory" in out
    
    # Working dir should be clean
    assert f.read_text() == "v1"
    
    # List stash
    main(["stash", "list"])
    out = capsys.readouterr().out
    assert "stash@{0}: WIP on main" in out


def test_stash_pop_clean(repo_with_commit: Path, capsys: pytest.CaptureFixture[str]) -> None:
    f = repo_with_commit / "f.txt"
    f.write_text("v2")
    
    # Save it
    main(["stash", "save"])
    
    # Verify cleaned
    assert f.read_text() == "v1"
    
    # Pop it
    capsys.readouterr()
    main(["stash", "pop"])
    out = capsys.readouterr().out
    assert "Dropped refs/stash@{0}" in out
    
    # Verify restored
    assert f.read_text() == "v2"


def test_stash_pop_with_conflict(repo_with_commit: Path, capsys: pytest.CaptureFixture[str]) -> None:
    f = repo_with_commit / "f.txt"
    
    # v2 -> stash
    f.write_text("v2")
    main(["stash"])  # default is save
    
    # Make a conflicting change and commit it so working dir is "clean" but base tree differs
    # Wait, simple way to create conflict:
    # f string is now v1. Change to v3, ADD and COMMIT.
    # Base is v1, Stash has v2. Current HEAD has v3.
    # 3-way merge will conflict.
    f.write_text("v3")
    main(["add", "f.txt"])
    main(["commit", "-m", "v3 commit"])
    
    # Now pop
    with pytest.raises(SystemExit) as exc:
        main(["stash", "pop"])
    assert exc.value.code == 1
    
    # Check that it kept OURS (v3)
    content = f.read_text(encoding="utf-8")
    assert content == "v3"
