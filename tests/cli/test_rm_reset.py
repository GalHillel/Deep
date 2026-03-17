"""
tests.test_rm_reset
~~~~~~~~~~~~~~~~~~~~
Tests for ``deep rm`` and ``deep reset``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from deep.storage.index import read_index
from deep.core.refs import resolve_head
from deep.cli.main import main


@pytest.fixture()
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    main(["init"])
    return tmp_path


def _commit(repo: Path, filename: str, content: str, msg: str) -> str:
    f = repo / filename
    f.write_text(content)
    main(["add", str(f)])
    main(["commit", "-m", msg])
    return resolve_head(repo / ".deep")


# ── rm tests ─────────────────────────────────────────────────────────

class TestRm:
    def test_rm_removes_file_and_index(self, repo: Path) -> None:
        f = repo / "a.txt"
        f.write_text("aaa")
        main(["add", str(f)])
        main(["rm", str(f)])
        assert not f.exists()
        idx = read_index(repo / ".deep")
        assert "a.txt" not in idx.entries

    def test_rm_untracked_fails(self, repo: Path) -> None:
        f = repo / "ghost.txt"
        f.write_text("boo")
        with pytest.raises(SystemExit):
            main(["rm", str(f)])

    def test_rm_multiple_files(self, repo: Path) -> None:
        a = repo / "a.txt"
        b = repo / "b.txt"
        a.write_text("a")
        b.write_text("b")
        main(["add", str(a), str(b)])
        main(["rm", str(a), str(b)])
        assert not a.exists()
        assert not b.exists()
        idx = read_index(repo / ".deep")
        assert len(idx.entries) == 0

    def test_rm_already_deleted_file(self, repo: Path) -> None:
        """If the file was already deleted from disk, rm should still remove from index."""
        f = repo / "del.txt"
        f.write_text("data")
        main(["add", str(f)])
        f.unlink()  # manually delete
        main(["rm", str(f)])  # should not error
        idx = read_index(repo / ".deep")
        assert "del.txt" not in idx.entries


# ── reset tests ──────────────────────────────────────────────────────

class TestReset:
    def test_soft_reset_moves_head(self, repo: Path) -> None:
        c1 = _commit(repo, "f.txt", "v1", "c1")
        c2 = _commit(repo, "f.txt", "v2", "c2")
        main(["reset", c1])
        assert resolve_head(repo / ".deep") == c1
        # Working dir should NOT be changed (soft reset).
        assert (repo / "f.txt").read_text() == "v2"

    def test_hard_reset_restores_files(self, repo: Path) -> None:
        c1 = _commit(repo, "f.txt", "v1", "c1")
        _commit(repo, "f.txt", "v2", "c2")
        main(["reset", "--hard", c1])
        assert resolve_head(repo / ".deep") == c1
        assert (repo / "f.txt").read_text() == "v1"

    def test_hard_reset_updates_index(self, repo: Path) -> None:
        c1 = _commit(repo, "f.txt", "v1", "c1")
        _commit(repo, "g.txt", "new", "c2")
        main(["reset", "--hard", c1])
        idx = read_index(repo / ".deep")
        assert "g.txt" not in idx.entries

    def test_reset_invalid_sha(self, repo: Path) -> None:
        _commit(repo, "f.txt", "v1", "c1")
        with pytest.raises(SystemExit):
            main(["reset", "0" * 40])

    def test_reset_round_trip(self, repo: Path) -> None:
        c1 = _commit(repo, "f.txt", "v1", "c1")
        c2 = _commit(repo, "f.txt", "v2", "c2")
        main(["reset", "--hard", c1])
        assert (repo / "f.txt").read_text() == "v1"
        main(["reset", "--hard", c2])
        assert (repo / "f.txt").read_text() == "v2"
