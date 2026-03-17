"""
tests.test_refs
~~~~~~~~~~~~~~~~
Unit tests for :mod:`deep.core.refs`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from deep.storage.objects import Blob, Commit, Tree, TreeEntry
from deep.core.refs import (
    delete_branch,
    get_branch,
    get_current_branch,
    head_is_symbolic,
    list_branches,
    log_history,
    resolve_head,
    update_branch,
    update_head,
)
from deep.core.repository import init_repo


# ── Helpers ──────────────────────────────────────────────────────────

def _make_commit(
    objects_dir: Path,
    message: str,
    parent_shas: list[str] | None = None,
    ts: int = 100,
) -> str:
    """Create a minimal blob→tree→commit and return the commit SHA."""
    b = Blob(data=message.encode())
    blob_sha = b.write(objects_dir)
    t = Tree(entries=[TreeEntry("100644", "f.txt", blob_sha)])
    tree_sha = t.write(objects_dir)
    c = Commit(
        tree_sha=tree_sha,
        parent_shas=parent_shas or [],
        message=message,
        timestamp=ts,
    )
    return c.write(objects_dir)


# ── HEAD tests ───────────────────────────────────────────────────────

class TestHead:
    def test_initial_head_is_symbolic(self, tmp_path: Path) -> None:
        dg = init_repo(tmp_path)
        assert head_is_symbolic(dg)

    def test_get_current_branch_initial(self, tmp_path: Path) -> None:
        dg = init_repo(tmp_path)
        assert get_current_branch(dg) == "main"

    def test_resolve_head_empty_repo(self, tmp_path: Path) -> None:
        dg = init_repo(tmp_path)
        assert resolve_head(dg) is None

    def test_resolve_head_after_commit(self, tmp_path: Path) -> None:
        dg = init_repo(tmp_path)
        sha = _make_commit(dg / "objects", "init")
        update_branch(dg, "main", sha)
        assert resolve_head(dg) == sha

    def test_detached_head(self, tmp_path: Path) -> None:
        dg = init_repo(tmp_path)
        sha = _make_commit(dg / "objects", "init")
        update_head(dg, sha)
        assert not head_is_symbolic(dg)
        assert resolve_head(dg) == sha
        assert get_current_branch(dg) is None


# ── Branch tests ─────────────────────────────────────────────────────

class TestBranch:
    def test_list_empty(self, tmp_path: Path) -> None:
        dg = init_repo(tmp_path)
        assert list_branches(dg) == []

    def test_create_and_get(self, tmp_path: Path) -> None:
        dg = init_repo(tmp_path)
        sha = _make_commit(dg / "objects", "first")
        update_branch(dg, "feature", sha)
        assert get_branch(dg, "feature") == sha
        assert "feature" in list_branches(dg)

    def test_update_existing_branch(self, tmp_path: Path) -> None:
        dg = init_repo(tmp_path)
        sha1 = _make_commit(dg / "objects", "v1", ts=1)
        sha2 = _make_commit(dg / "objects", "v2", parent_shas=[sha1], ts=2)
        update_branch(dg, "main", sha1)
        update_branch(dg, "main", sha2)
        assert get_branch(dg, "main") == sha2

    def test_delete_branch(self, tmp_path: Path) -> None:
        dg = init_repo(tmp_path)
        sha = _make_commit(dg / "objects", "x")
        update_branch(dg, "temp", sha)
        delete_branch(dg, "temp")
        assert get_branch(dg, "temp") is None

    def test_delete_nonexistent_raises(self, tmp_path: Path) -> None:
        dg = init_repo(tmp_path)
        with pytest.raises(FileNotFoundError):
            delete_branch(dg, "ghost")

    def test_delete_current_branch_raises(self, tmp_path: Path) -> None:
        dg = init_repo(tmp_path)
        sha = _make_commit(dg / "objects", "x")
        update_branch(dg, "main", sha)
        with pytest.raises(ValueError, match="currently checked-out"):
            delete_branch(dg, "main")

    def test_get_nonexistent_returns_none(self, tmp_path: Path) -> None:
        dg = init_repo(tmp_path)
        assert get_branch(dg, "nope") is None


# ── DAG traversal (log) ─────────────────────────────────────────────

class TestLogHistory:
    def test_empty_repo(self, tmp_path: Path) -> None:
        dg = init_repo(tmp_path)
        assert log_history(dg) == []

    def test_single_commit(self, tmp_path: Path) -> None:
        dg = init_repo(tmp_path)
        sha = _make_commit(dg / "objects", "first")
        update_branch(dg, "main", sha)
        assert log_history(dg) == [sha]

    def test_chain_of_commits(self, tmp_path: Path) -> None:
        dg = init_repo(tmp_path)
        c1 = _make_commit(dg / "objects", "c1", ts=1)
        c2 = _make_commit(dg / "objects", "c2", parent_shas=[c1], ts=2)
        c3 = _make_commit(dg / "objects", "c3", parent_shas=[c2], ts=3)
        update_branch(dg, "main", c3)
        history = log_history(dg)
        assert history == [c3, c2, c1]

    def test_max_count(self, tmp_path: Path) -> None:
        dg = init_repo(tmp_path)
        c1 = _make_commit(dg / "objects", "c1", ts=1)
        c2 = _make_commit(dg / "objects", "c2", parent_shas=[c1], ts=2)
        c3 = _make_commit(dg / "objects", "c3", parent_shas=[c2], ts=3)
        update_branch(dg, "main", c3)
        assert log_history(dg, max_count=2) == [c3, c2]

    def test_explicit_start_sha(self, tmp_path: Path) -> None:
        dg = init_repo(tmp_path)
        c1 = _make_commit(dg / "objects", "c1", ts=1)
        c2 = _make_commit(dg / "objects", "c2", parent_shas=[c1], ts=2)
        update_branch(dg, "main", c2)
        assert log_history(dg, start_sha=c1) == [c1]
