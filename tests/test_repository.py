"""
tests.test_repository
~~~~~~~~~~~~~~~~~~~~~~
Unit tests for :mod:`deep.core.repository`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from deep.core.repository import DEEP_GIT_DIR, find_repo, init_repo


class TestInitRepo:
    """Verify repository initialisation."""

    def test_creates_directory_structure(self, tmp_path: Path) -> None:
        dg = init_repo(tmp_path)
        assert dg == tmp_path / DEEP_GIT_DIR
        assert (dg / "objects").is_dir()
        assert (dg / "refs" / "heads").is_dir()
        assert (dg / "HEAD").is_file()
        assert (dg / "index").is_file()

    def test_head_points_to_main(self, tmp_path: Path) -> None:
        dg = init_repo(tmp_path)
        head = (dg / "HEAD").read_text()
        assert head.strip() == "ref: refs/heads/main"

    def test_index_is_valid_json(self, tmp_path: Path) -> None:
        dg = init_repo(tmp_path)
        data = json.loads((dg / "index").read_text())
        assert "entries" in data
        assert data["entries"] == {}

    def test_raises_if_already_exists(self, tmp_path: Path) -> None:
        init_repo(tmp_path)
        with pytest.raises(FileExistsError):
            init_repo(tmp_path)

    def test_creates_repo_root_if_needed(self, tmp_path: Path) -> None:
        new_dir = tmp_path / "brand_new"
        dg = init_repo(new_dir)
        assert dg.is_dir()


class TestFindRepo:
    """Verify repository discovery by walking up the tree."""

    def test_finds_from_root(self, tmp_path: Path) -> None:
        init_repo(tmp_path)
        assert find_repo(tmp_path) == tmp_path.resolve()

    def test_finds_from_subdirectory(self, tmp_path: Path) -> None:
        init_repo(tmp_path)
        child = tmp_path / "a" / "b" / "c"
        child.mkdir(parents=True)
        assert find_repo(child) == tmp_path.resolve()

    def test_raises_if_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            find_repo(tmp_path)
