"""
tests.test_cli
~~~~~~~~~~~~~~~
End-to-end integration tests for the Deep Git CLI.

Each test creates a fresh temporary repo and exercises the CLI by calling
:func:`deep.main.main` directly with argv lists.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from deep.cli.main import main
from deep.core.repository import DEEP_GIT_DIR


@pytest.fixture()
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create a fresh repo in *tmp_path* and chdir into it."""
    monkeypatch.chdir(tmp_path)
    main(["init"])
    return tmp_path


# ── init ─────────────────────────────────────────────────────────────

class TestInitCLI:
    def test_init_creates_deep_git_dir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        main(["init"])
        assert (tmp_path / DEEP_GIT_DIR).is_dir()

    def test_init_with_path(self, tmp_path: Path) -> None:
        target = tmp_path / "my_repo"
        main(["init", str(target)])
        assert (target / DEEP_GIT_DIR).is_dir()

    def test_init_twice_fails(self, repo: Path) -> None:
        with pytest.raises(SystemExit):
            main(["init"])


# ── add ──────────────────────────────────────────────────────────────

class TestAddCLI:
    def test_add_single_file(self, repo: Path) -> None:
        f = repo / "hello.txt"
        f.write_text("hello")
        main(["add", str(f)])
        # Verify the index has the entry.
        from deep.storage.index import read_index
        idx = read_index(repo / DEEP_GIT_DIR)
        assert "hello.txt" in idx.entries

    def test_add_multiple_files(self, repo: Path) -> None:
        a = repo / "a.txt"
        b = repo / "b.txt"
        a.write_text("aaa")
        b.write_text("bbb")
        main(["add", str(a), str(b)])
        from deep.storage.index import read_index
        idx = read_index(repo / DEEP_GIT_DIR)
        assert "a.txt" in idx.entries
        assert "b.txt" in idx.entries

    def test_add_nonexistent_file_fails(self, repo: Path) -> None:
        with pytest.raises(SystemExit):
            main(["add", "ghost.txt"])


# ── commit ───────────────────────────────────────────────────────────

class TestCommitCLI:
    def test_commit_creates_objects(self, repo: Path) -> None:
        f = repo / "data.txt"
        f.write_text("data")
        main(["add", str(f)])
        main(["commit", "-m", "initial commit"])
        # HEAD should now resolve to a commit.
        from deep.core.refs import resolve_head
        sha = resolve_head(repo / DEEP_GIT_DIR)
        assert sha is not None and len(sha) == 40

    def test_commit_empty_index_fails(self, repo: Path) -> None:
        with pytest.raises(SystemExit):
            main(["commit", "-m", "empty"])

    def test_two_commits_form_chain(self, repo: Path) -> None:
        f = repo / "x.txt"
        f.write_text("v1")
        main(["add", str(f)])
        main(["commit", "-m", "first"])

        f.write_text("v2")
        main(["add", str(f)])
        main(["commit", "-m", "second"])

        from deep.core.refs import log_history
        history = log_history(repo / DEEP_GIT_DIR)
        assert len(history) == 2


# ── log ──────────────────────────────────────────────────────────────

class TestLogCLI:
    def test_log_empty_repo(self, repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        main(["log"])
        out = capsys.readouterr().out
        assert "No commits yet" in out

    def test_log_shows_message(self, repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        f = repo / "m.txt"
        f.write_text("m")
        main(["add", str(f)])
        main(["commit", "-m", "my message"])
        main(["log"])
        out = capsys.readouterr().out
        assert "my message" in out
        assert "commit " in out


# ── branch ───────────────────────────────────────────────────────────

class TestBranchCLI:
    def test_branch_list_no_commits(self, repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        main(["branch"])
        out = capsys.readouterr().out
        assert "No branches" in out

    def test_create_branch(self, repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        f = repo / "b.txt"
        f.write_text("b")
        main(["add", str(f)])
        main(["commit", "-m", "base"])
        main(["branch", "feature"])
        out = capsys.readouterr().out
        assert "Created branch 'feature'" in out

    def test_list_branches_after_create(self, repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        f = repo / "c.txt"
        f.write_text("c")
        main(["add", str(f)])
        main(["commit", "-m", "base"])
        main(["branch", "dev"])
        # Clear captured output from commit & branch create.
        capsys.readouterr()
        main(["branch"])
        out = capsys.readouterr().out
        assert "* main" in out
        assert "  dev" in out

    def test_create_branch_no_commits_fails(self, repo: Path) -> None:
        with pytest.raises(SystemExit):
            main(["branch", "oops"])


# ── Full workflow ────────────────────────────────────────────────────

class TestFullWorkflow:
    """End-to-end: init → add → commit → branch → log."""

    def test_complete_flow(self, repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        # Create and add files.
        (repo / "readme.md").write_text("# Hello")
        (repo / "main.py").write_text("print('hi')")
        main(["add", str(repo / "readme.md"), str(repo / "main.py")])

        # First commit.
        main(["commit", "-m", "Initial commit"])

        # Create a branch.
        main(["branch", "develop"])

        # Modify and make a second commit.
        (repo / "main.py").write_text("print('updated')")
        main(["add", str(repo / "main.py")])
        main(["commit", "-m", "Update main.py"])

        # Clear output so far.
        capsys.readouterr()

        # Log should show two commits, newest first.
        main(["log"])
        out = capsys.readouterr().out
        assert "Update main.py" in out
        assert "Initial commit" in out
        # "Update main.py" should appear BEFORE "Initial commit".
        assert out.index("Update main.py") < out.index("Initial commit")

        # Branch listing.
        capsys.readouterr()
        main(["branch"])
        out = capsys.readouterr().out
        assert "* main" in out
        assert "  develop" in out
