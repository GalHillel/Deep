"""
tests.test_gc
~~~~~~~~~~~~~
Tests for Mark-and-Sweep Garbage Collection.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from deep.core.repository import DEEP_GIT_DIR
from deep.core.refs import delete_branch
from deep.cli.main import main


@pytest.fixture()
def repo_with_orphan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, str]:
    monkeypatch.chdir(tmp_path)
    main(["init"])
    
    # Commit 1 (base)
    (tmp_path / "base.txt").write_text("base")
    main(["add", "base.txt"])
    main(["commit", "-m", "base"])
    
    # Create branch 'orphan-branch'
    main(["branch", "orphan-branch"])
    main(["checkout", "orphan-branch"])
    
    # Commit 2 (on orphan-branch)
    f = tmp_path / "orphan.txt"
    f.write_text("orphan content")
    main(["add", "orphan.txt"])
    main(["commit", "-m", "orphan commit"])
    
    orphan_sha = (tmp_path / DEEP_GIT_DIR / "refs" / "heads" / "orphan-branch").read_text().strip()
    
    # Checkout main and delete orphan-branch
    main(["checkout", "main"])
    delete_branch(tmp_path / DEEP_GIT_DIR, "orphan-branch")
    
    return tmp_path, orphan_sha


def test_gc_collects_orphan(repo_with_orphan: tuple[Path, str], capsys: pytest.CaptureFixture[str]) -> None:
    repo_root, orphan_sha = repo_with_orphan
    dg_dir = repo_root / DEEP_GIT_DIR
    objects_dir = dg_dir / "objects"
    
    # Verify orphan object exists
    orphan_path = objects_dir / orphan_sha[:2] / orphan_sha[2:]
    assert orphan_path.exists()
    
    # Run GC
    main(["gc"])
    out = capsys.readouterr().out
    assert "Relocated" in out
    
    # Verify orphan SHA is gone from objects but in quarantine
    assert not orphan_path.exists()
    
    quarantine_base = dg_dir / "quarantine"
    assert quarantine_base.exists()
    
    # Check if ANY file in quarantine has our orphan SHA name
    quarantined_files = list(quarantine_base.glob("**/"+orphan_sha))
    assert quarantined_files


def test_gc_dry_run(repo_with_orphan: tuple[Path, str], capsys: pytest.CaptureFixture[str]) -> None:
    repo_root, orphan_sha = repo_with_orphan
    dg_dir = repo_root / DEEP_GIT_DIR
    objects_dir = dg_dir / "objects"
    
    orphan_path = objects_dir / orphan_sha[:2] / orphan_sha[2:]
    assert orphan_path.exists()
    
    # Run GC Dry Run
    main(["gc", "--dry-run", "--verbose"])
    out = capsys.readouterr().out
    assert "Would quarantine: " + orphan_sha in out
    
    # Verify nothing moved
    assert orphan_path.exists()
    assert not (dg_dir / "quarantine").exists()


def test_gc_preserves_reachable(repo_with_orphan: tuple[Path, str], capsys: pytest.CaptureFixture[str]) -> None:
    repo_root, _ = repo_with_orphan
    dg_dir = repo_root / DEEP_GIT_DIR
    
    # Tag a new commit so it's reachable only via tag
    (repo_root / "tag.txt").write_text("tagged")
    main(["add", "tag.txt"])
    main(["commit", "-m", "tagged commit"])
    
    from deep.core.refs import resolve_head
    tagged_sha = resolve_head(dg_dir)
    assert tagged_sha
    
    main(["tag", "my-tag"])
    
    # HEAD is already at 'tagged commit' on branch main.
    # GC should preserve it because it's reachable via HEAD, main branch, and tag.
    
    main(["gc"])
    capsys.readouterr()  # consume output
    
    # Verify the object is still readable (may be in packfile after GC)
    from deep.storage.objects import read_object
    objects_dir = dg_dir / "objects"
    obj = read_object(objects_dir, tagged_sha)
    assert obj is not None


def test_gc_preserves_stash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.chdir(tmp_path)
    main(["init"])
    
    (tmp_path / "f.txt").write_text("v1")
    main(["add", "f.txt"])
    main(["commit", "-m", "c1"])
    
    (tmp_path / "f.txt").write_text("v2")
    main(["stash", "save"])
    
    from deep.core.stash import get_stash_list
    stashes = get_stash_list(tmp_path / DEEP_GIT_DIR)
    assert stashes
    stash_sha = stashes[0]
    
    # Run GC
    main(["gc"])
    
    # Verify stash object is still readable (may be in packfile after GC)
    dg_dir = tmp_path / DEEP_GIT_DIR
    objects_dir = dg_dir / "objects"
    from deep.storage.objects import read_object
    obj = read_object(objects_dir, stash_sha)
    assert obj is not None

