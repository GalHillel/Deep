"""
tests.test_checkout
~~~~~~~~~~~~~~~~~~~~
Tests for ``deep checkout``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from deep.storage.index import read_index
from deep.core.refs import get_current_branch, resolve_head
from deep.cli.main import main
from deep.core.errors import DeepCLIException


@pytest.fixture()
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    main(["init"])
    return tmp_path


class TestCheckout:
    def _make_commit(self, repo: Path, filename: str, content: str, msg: str) -> None:
        f = repo / filename
        f.write_text(content)
        main(["add", str(f)])
        main(["commit", "-m", msg])

    def test_checkout_branch(self, repo: Path) -> None:
        self._make_commit(repo, "f.txt", "v1", "c1")
        main(["branch", "dev"])
        # Make a second commit on main.
        self._make_commit(repo, "f.txt", "v2", "c2")
        # Checkout dev (which points to c1).
        main(["checkout", "dev"])
        assert get_current_branch(repo / ".deep") == "dev"
        assert (repo / "f.txt").read_text() == "v1"

    def test_checkout_detached(self, repo: Path) -> None:
        self._make_commit(repo, "f.txt", "data", "c1")
        sha = resolve_head(repo / ".deep")
        self._make_commit(repo, "f.txt", "data2", "c2")
        main(["checkout", sha])
        assert get_current_branch(repo / ".deep") is None
        assert (repo / "f.txt").read_text() == "data"

    def test_checkout_refuses_with_uncommitted(self, repo: Path) -> None:
        self._make_commit(repo, "f.txt", "v1", "c1")
        main(["branch", "dev"])
        main(["checkout", "dev"])
        self._make_commit(repo, "f.txt", "v-dev", "c-dev")
        main(["checkout", "main"]) # Back to main (f.txt=v1)
        
        (repo / "f.txt").write_text("dirty")
        with pytest.raises(DeepCLIException):
            main(["checkout", "dev"]) # Should fail because dev has v-dev, we have dirty v1

    def test_checkout_updates_index(self, repo: Path) -> None:
        self._make_commit(repo, "a.txt", "aaa", "c1")
        main(["branch", "alt"])
        self._make_commit(repo, "b.txt", "bbb", "c2")
        main(["checkout", "alt"])
        idx = read_index(repo / ".deep")
        assert "a.txt" in idx.entries
        assert "b.txt" not in idx.entries

    def test_checkout_invalid_target(self, repo: Path) -> None:
        self._make_commit(repo, "f.txt", "x", "c1")
        with pytest.raises(DeepCLIException):
            main(["checkout", "nonexistent"])

    def test_round_trip_checkout(self, repo: Path) -> None:
        """Switch branches and come back; file contents must round-trip."""
        self._make_commit(repo, "f.txt", "on_main", "main commit")
        main(["branch", "other"])
        # Modify on main.
        self._make_commit(repo, "f.txt", "main_v2", "main v2")
        # Go to other branch.
        main(["checkout", "other"])
        assert (repo / "f.txt").read_text() == "on_main"
        # Come back to main.
        main(["checkout", "main"])
        assert (repo / "f.txt").read_text() == "main_v2"
