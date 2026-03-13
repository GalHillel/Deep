"""
tests.test_mv
~~~~~~~~~~~~~~
Tests for ``deep mv``.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from deep.storage.index import read_index
from deep.core.repository import DEEP_DIR
from deep.cli.main import main


@pytest.fixture()
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    main(["init"])
    return tmp_path


def test_mv_file(repo: Path) -> None:
    # 1. Add file
    file1 = repo / "file1.txt"
    file1.write_text("hello 1")
    main(["add", "file1.txt"])

    index_entries = read_index(repo / DEEP_DIR).entries
    assert "file1.txt" in index_entries

    # 2. Rename file
    main(["mv", "file1.txt", "file2.txt"])

    # 3. Assert on disk
    assert not file1.exists()
    assert (repo / "file2.txt").exists()
    assert (repo / "file2.txt").read_text() == "hello 1"

    # 4. Assert in index
    index_entries_after = read_index(repo / DEEP_DIR).entries
    assert "file1.txt" not in index_entries_after
    assert "file2.txt" in index_entries_after

def test_mv_directory(repo: Path) -> None:
    # 1. Add directory
    dir1 = repo / "dir1"
    dir1.mkdir()
    (dir1 / "file.txt").write_text("dir file")
    main(["add", "."])

    index_entries = read_index(repo / DEEP_DIR).entries
    assert "dir1/file.txt" in index_entries

    # 2. Move directory
    main(["mv", "dir1", "dir2"])

    # 3. Assert on disk
    assert not dir1.exists()
    assert (repo / "dir2" / "file.txt").exists()

    # 4. Assert in index
    index_entries_after = read_index(repo / DEEP_DIR).entries
    assert "dir1/file.txt" not in index_entries_after
    assert "dir2/file.txt" in index_entries_after
