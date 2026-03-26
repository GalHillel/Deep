"""
tests.test_doctor
~~~~~~~~~~~~~~~~~
Tests for the repository integrity guard (deep doctor).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from deep.core.repository import DEEP_DIR
from deep.core.refs import update_branch, update_head
from deep.cli.main import main
from deep.core.errors import DeepCLIException


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
    assert "Repository consistent" in out
    assert "0 warnings" in out


def test_doctor_corrupt_object(clean_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    dg_dir = clean_repo / DEEP_DIR
    objects_dir = dg_dir / "objects"
    
    # Find any object file
    obj_files = [f for f in objects_dir.rglob("*") if f.is_file() and len(f.name) >= 36]
    assert obj_files
    
    import stat
    # Corrupt it by truncating
    os.chmod(obj_files[0], stat.S_IWRITE)
    obj_files[0].write_bytes(b"corrupt data")
    
    with pytest.raises(SystemExit) as exc:
        main(["doctor"])
        
    assert exc.value.code == 1
    captured = capsys.readouterr()
    # The corruption may be caught by main.py's startup integrity check (stderr)
    # or by the doctor scan itself (stdout). Either path is valid hardening behavior.
    combined = captured.out + captured.err
    assert "corrupt" in combined.lower() or "integrity" in combined.lower() or "fatal" in combined.lower()


def test_doctor_missing_ref_target(clean_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    dg_dir = clean_repo / DEEP_DIR
    
    # Make a branch pointing to nowhere
    fake_sha = "1" * 40
    update_branch(dg_dir, "fake-branch", fake_sha)
    
    with pytest.raises(DeepCLIException) as exc:
        main(["doctor"])
        
    assert exc.value.code == 1
    out = capsys.readouterr().err
    assert "FATAL: Repository corrupted" in out
    assert f"Branch 'fake-branch' points to invalid object {fake_sha}" in out


def test_doctor_missing_head(clean_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    dg_dir = clean_repo / DEEP_DIR
    
    # Point head to nowhere
    fake_sha = "2" * 40
    update_head(dg_dir, fake_sha)
    
    with pytest.raises(DeepCLIException) as exc:
        main(["doctor"])
        
    assert exc.value.code == 1
    out = capsys.readouterr().err
    assert "FATAL: Repository corrupted" in out
    assert f"HEAD points to invalid object {fake_sha}" in out
