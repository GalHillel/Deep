"""
tests.test_diff
~~~~~~~~~~~~~~~~
Tests for :mod:`deep_git.core.diff` and ``deepgit diff`` command.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from deep_git.core.diff import diff_lines, diff_working_tree
from deep_git.main import main


@pytest.fixture()
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    main(["init"])
    return tmp_path


class TestDiffLines:
    def test_identical(self) -> None:
        assert diff_lines(["a", "b"], ["a", "b"]) == ""

    def test_addition(self) -> None:
        result = diff_lines(["a"], ["a", "b"])
        assert "+b" in result

    def test_deletion(self) -> None:
        result = diff_lines(["a", "b"], ["a"])
        assert "-b" in result

    def test_modification(self) -> None:
        result = diff_lines(["hello"], ["world"])
        assert "-hello" in result
        assert "+world" in result


class TestDiffWorkingTree:
    def test_no_diff_on_clean_tree(self, repo: Path) -> None:
        f = repo / "f.txt"
        f.write_text("data")
        main(["add", str(f)])
        diffs = diff_working_tree(repo)
        assert diffs == []

    def test_diff_after_modification(self, repo: Path) -> None:
        f = repo / "f.txt"
        f.write_text("line1")
        main(["add", str(f)])
        f.write_text("line1\nline2")
        diffs = diff_working_tree(repo)
        assert len(diffs) == 1
        rel_path, diff_text = diffs[0]
        assert rel_path == "f.txt"
        assert "+line2" in diff_text

    def test_diff_deleted_file(self, repo: Path) -> None:
        f = repo / "f.txt"
        f.write_text("gone")
        main(["add", str(f)])
        f.unlink()
        diffs = diff_working_tree(repo)
        assert len(diffs) == 1
        assert "-gone" in diffs[0][1]

    def test_multiple_file_diffs(self, repo: Path) -> None:
        a = repo / "a.txt"
        b = repo / "b.txt"
        a.write_text("a1")
        b.write_text("b1")
        main(["add", str(a), str(b)])
        a.write_text("a2")
        b.write_text("b2")
        diffs = diff_working_tree(repo)
        assert len(diffs) == 2


class TestDiffCLI:
    def test_diff_shows_output(self, repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        f = repo / "x.txt"
        f.write_text("old")
        main(["add", str(f)])
        f.write_text("new")
        main(["diff"])
        out = capsys.readouterr().out
        assert "-old" in out
        assert "+new" in out

    def test_diff_clean_no_output(self, repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        f = repo / "x.txt"
        f.write_text("same")
        main(["add", str(f)])
        capsys.readouterr()  # clear output from add
        main(["diff"])
        out = capsys.readouterr().out
        assert out == ""
