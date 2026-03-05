"""
tests.test_merge
~~~~~~~~~~~~~~~~~
Tests for :mod:`deep.core.merge` and ``deep merge`` command.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from deep.core.merge import find_lca, three_way_merge
from deep.storage.objects import Blob, Commit, Tree, TreeEntry, read_object
from deep.core.refs import resolve_head, get_branch
from deep.cli.main import main
from deep.core.repository import init_repo, DEEP_GIT_DIR


@pytest.fixture()
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    main(["init"])
    return tmp_path


def _commit(repo: Path, filename: str, content: str, msg: str) -> None:
    f = repo / filename
    f.write_text(content)
    main(["add", str(f)])
    main(["commit", "-m", msg])


# ── LCA tests ───────────────────────────────────────────────────────

class TestFindLCA:
    def test_linear_lca(self, repo: Path) -> None:
        dg = repo / DEEP_GIT_DIR
        _commit(repo, "f.txt", "v1", "c1")
        c1 = resolve_head(dg)
        _commit(repo, "f.txt", "v2", "c2")
        c2 = resolve_head(dg)
        lca = find_lca(dg / "objects", c1, c2)
        assert lca == c1

    def test_diverged_lca(self, repo: Path) -> None:
        dg = repo / DEEP_GIT_DIR
        _commit(repo, "f.txt", "base", "base")
        base = resolve_head(dg)
        main(["branch", "feature"])
        # Commit on main.
        _commit(repo, "f.txt", "main_v2", "main c2")
        main_head = resolve_head(dg)
        # Checkout feature and commit.
        main(["checkout", "feature"])
        _commit(repo, "g.txt", "feature_new", "feat c1")
        feat_head = resolve_head(dg)
        lca = find_lca(dg / "objects", main_head, feat_head)
        assert lca == base


# ── Merge command tests ──────────────────────────────────────────────

class TestMerge:
    def test_already_up_to_date(self, repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        _commit(repo, "f.txt", "v1", "c1")
        main(["branch", "same"])
        capsys.readouterr()
        main(["merge", "same"])
        out = capsys.readouterr().out
        assert "Already up to date" in out

    def test_fast_forward(self, repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        _commit(repo, "f.txt", "v1", "c1")
        main(["branch", "feature"])
        main(["checkout", "feature"])
        _commit(repo, "g.txt", "new", "feat commit")
        main(["checkout", "main"])
        capsys.readouterr()
        main(["merge", "feature"])
        out = capsys.readouterr().out
        assert "Fast-forward" in out
        # The new file should be in working dir now.
        assert (repo / "g.txt").read_text() == "new"

    def test_fast_forward_updates_branch(self, repo: Path) -> None:
        dg = repo / DEEP_GIT_DIR
        _commit(repo, "f.txt", "v1", "c1")
        main(["branch", "feature"])
        main(["checkout", "feature"])
        _commit(repo, "g.txt", "new", "feat commit")
        feat_head = resolve_head(dg)
        main(["checkout", "main"])
        main(["merge", "feature"])
        assert resolve_head(dg) == feat_head

    def test_three_way_merge_no_conflict(self, repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        _commit(repo, "f.txt", "base", "base")
        main(["branch", "feature"])
        # Commit on main — modify f.txt.
        _commit(repo, "f.txt", "main_change", "main c2")
        # Checkout feature — add a new file.
        main(["checkout", "feature"])
        _commit(repo, "g.txt", "feat_new", "feat c1")
        main(["checkout", "main"])
        capsys.readouterr()
        main(["merge", "feature"])
        out = capsys.readouterr().out
        assert "Merge made" in out
        # Both files should exist.
        assert (repo / "f.txt").read_text() == "main_change"
        assert (repo / "g.txt").read_text() == "feat_new"

    def test_conflict_aborts(self, repo: Path) -> None:
        _commit(repo, "f.txt", "base", "base")
        main(["branch", "feature"])
        _commit(repo, "f.txt", "main_v", "main change")
        main(["checkout", "feature"])
        _commit(repo, "f.txt", "feat_v", "feat change")
        main(["checkout", "main"])
        with pytest.raises(SystemExit):
            main(["merge", "feature"])

    def test_nonexistent_branch(self, repo: Path) -> None:
        _commit(repo, "f.txt", "v1", "c1")
        with pytest.raises(SystemExit):
            main(["merge", "ghost"])
