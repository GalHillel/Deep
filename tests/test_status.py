"""
tests.test_status
~~~~~~~~~~~~~~~~~~
Tests for :mod:`deep_git.core.status` and ``deepgit status`` command.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from deep_git.core.status import compute_status
from deep_git.main import main


@pytest.fixture()
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create a fresh repo and chdir into it."""
    monkeypatch.chdir(tmp_path)
    main(["init"])
    return tmp_path


class TestStatusEngine:
    """Unit tests for compute_status."""

    def test_clean_empty_repo(self, repo: Path) -> None:
        status = compute_status(repo)
        assert status.staged_new == []
        assert status.modified == []
        assert status.untracked == []

    def test_untracked_file(self, repo: Path) -> None:
        (repo / "new.txt").write_text("hello")
        status = compute_status(repo)
        assert "new.txt" in status.untracked

    def test_staged_new_file(self, repo: Path) -> None:
        (repo / "a.txt").write_text("aaa")
        main(["add", str(repo / "a.txt")])
        status = compute_status(repo)
        assert "a.txt" in status.staged_new
        assert "a.txt" not in status.untracked

    def test_modified_after_staging(self, repo: Path) -> None:
        f = repo / "m.txt"
        f.write_text("v1")
        main(["add", str(f)])
        main(["commit", "-m", "c1"])
        # Modify after commit.
        f.write_text("v2")
        status = compute_status(repo)
        assert "m.txt" in status.modified

    def test_clean_after_commit(self, repo: Path) -> None:
        f = repo / "c.txt"
        f.write_text("data")
        main(["add", str(f)])
        main(["commit", "-m", "done"])
        status = compute_status(repo)
        assert status.staged_new == []
        assert status.modified == []
        assert status.untracked == []
        assert status.deleted == []

    def test_deleted_file(self, repo: Path) -> None:
        f = repo / "d.txt"
        f.write_text("delete me")
        main(["add", str(f)])
        main(["commit", "-m", "add"])
        f.unlink()
        status = compute_status(repo)
        assert "d.txt" in status.deleted

    def test_staged_modified(self, repo: Path) -> None:
        """File committed, then modified and re-staged → staged_modified."""
        f = repo / "s.txt"
        f.write_text("v1")
        main(["add", str(f)])
        main(["commit", "-m", "v1"])
        f.write_text("v2")
        main(["add", str(f)])
        status = compute_status(repo)
        assert "s.txt" in status.staged_modified

    def test_mixed_status(self, repo: Path) -> None:
        """Multiple files with different statuses."""
        # Committed file.
        (repo / "committed.txt").write_text("ok")
        main(["add", str(repo / "committed.txt")])
        main(["commit", "-m", "init"])

        # Untracked file.
        (repo / "untracked.txt").write_text("new")

        # Modified file (tracked but changed).
        (repo / "committed.txt").write_text("changed")

        status = compute_status(repo)
        assert "untracked.txt" in status.untracked
        assert "committed.txt" in status.modified


class TestStatusCLI:
    """Integration tests for ``deepgit status``."""

    def test_clean_output(self, repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        main(["status"])
        out = capsys.readouterr().out
        assert "nothing to commit" in out

    def test_shows_untracked(self, repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        (repo / "u.txt").write_text("u")
        main(["status"])
        out = capsys.readouterr().out
        assert "Untracked files:" in out
        assert "u.txt" in out

    def test_shows_staged(self, repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        (repo / "s.txt").write_text("s")
        main(["add", str(repo / "s.txt")])
        main(["status"])
        out = capsys.readouterr().out
        assert "Changes to be committed:" in out
        assert "new file:" in out
