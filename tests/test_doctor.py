"""
tests.test_doctor
~~~~~~~~~~~~~~~~~
Tests for the repository integrity guard (deepgit doctor).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from deep_git.core.repository import DEEP_GIT_DIR
from deep_git.core.refs import update_branch, update_head
from deep_git.main import main


@pytest.fixture()
def clean_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    main(["init"])
    
    # Make a few clean commits
    for i in range(2):
        f = tmp_path / f"file{i}.txt"
        f.write_text(f"content {i}")
        main(["add", str(f.name)])
        main(["commit", "-m", f"commit {i}"])
        
    main(["tag", "v1.0"])
    
    return tmp_path


def test_doctor_clean(clean_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # A clean repo should pass doctor
    main(["doctor"])
    out = capsys.readouterr().out
    assert "Repository is clean and consistent." in out
    assert "0 errors" in out


def test_doctor_corrupt_object(clean_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    dg_dir = clean_repo / DEEP_GIT_DIR
    objects_dir = dg_dir / "objects"
    
    # Find any object file
    obj_files = list(objects_dir.glob("??/*"))
    assert obj_files
    
    # Corrupt it by truncating
    obj_files[0].write_bytes(b"corrupt data")
    
    with pytest.raises(SystemExit) as exc:
        main(["doctor"])
        
    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert "Repository integrity compromised." in out
    assert "Found" in out
    assert "errors" in out


def test_doctor_missing_ref_target(clean_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    dg_dir = clean_repo / DEEP_GIT_DIR
    
    # Make a branch pointing to nowhere
    fake_sha = "1" * 40
    update_branch(dg_dir, "fake-branch", fake_sha)
    
    with pytest.raises(SystemExit) as exc:
        main(["doctor"])
        
    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert f"Branch 'fake-branch' points to missing commit {fake_sha[:7]}" in out


def test_doctor_missing_head(clean_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    dg_dir = clean_repo / DEEP_GIT_DIR
    
    # Point head to nowhere
    fake_sha = "2" * 40
    update_head(dg_dir, fake_sha)
    
    with pytest.raises(SystemExit) as exc:
        main(["doctor"])
        
    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert f"HEAD points to missing commit {fake_sha[:7]}" in out
