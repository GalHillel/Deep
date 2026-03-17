"""
tests.test_doctor_autofix
~~~~~~~~~~~~~~~~~~~~~~~~~
Tests for `deep doctor --fix` and dangling object detection.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from deep.core.repository import DEEP_DIR
from deep.storage.objects import Blob
from deep.cli.main import main


@pytest.fixture()
def clean_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    main(["init"])
    
    # Make a clean commit
    f = tmp_path / "file.txt"
    f.write_text("tracked content")
    main(["add", "file.txt"])
    main(["commit", "-m", "commit 1"])
    
    return tmp_path


def test_doctor_detects_dangling(clean_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    dg_dir = clean_repo / DEEP_DIR
    objects_dir = dg_dir / "objects"
    
    # Create a dangling blob manually
    b = Blob(data=b"dangling content")
    dangling_sha = b.write(objects_dir)
    
    main(["doctor"])
    out = capsys.readouterr().out
    
    assert "1 dangling objects found" in out
    assert "Repository consistent. 1 warnings." in out  # Only warnings, no errors


def test_doctor_fix_quarantines_dangling(clean_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    dg_dir = clean_repo / DEEP_DIR
    objects_dir = dg_dir / "objects"
    
    # Create a dangling blob manually
    b = Blob(data=b"dangling content")
    dangling_sha = b.write(objects_dir)
    
    # Run with --fix
    main(["doctor", "--fix"])
    out = capsys.readouterr().out
    
    assert "1 dangling objects found" in out
    assert "Applying fixes..." in out
    assert f"Fixed: Quarantined dangling object {dangling_sha}" in out
    
    # Verify it was quarantined
    assert not (objects_dir / dangling_sha[:2] / dangling_sha[2:]).exists()
    
    quarantine_base = dg_dir / "quarantine"
    assert quarantine_base.exists()
    quarantined_files = list(quarantine_base.glob(f"**/{dangling_sha}"))
    assert quarantined_files


def test_doctor_fix_quarantines_corrupt(clean_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    dg_dir = clean_repo / DEEP_DIR
    objects_dir = dg_dir / "objects"
    
    # Create a dangling blob manually, and corrupt it
    b = Blob(data=b"content")
    sha = b.write(objects_dir)
    obj_path = objects_dir / sha[:2] / sha[2:]
    
    # Corrupt the file
    obj_path.write_bytes(b"corrupt data")
    
    # Run with --fix
    main(["doctor", "--fix"])
    
    combined = capsys.readouterr()
    out = combined.out + combined.err
    
    assert "Applying fixes..." in out
    assert f"Fixed: Quarantined corrupt object {sha}" in out
    
    # Verify it was quarantined
    assert not obj_path.exists()
    
    quarantine_base = dg_dir / "quarantine"
    assert quarantine_base.exists()
    quarantined_files = list(quarantine_base.glob(f"**/{sha}_corrupt"))
    assert quarantined_files
