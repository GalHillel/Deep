"""
tests.test_init_recovery
~~~~~~~~~~~~~~~~~~~~~~~~

Recovery and idempotence tests for :mod:`deep.core.repository` and
the foundational status/index behaviour.
"""

from __future__ import annotations

from pathlib import Path

from deep.core.repository import DEEP_DIR, init_repo
from deep.core.status import compute_status
from deep.storage.index import read_index


def test_init_repairs_missing_head(tmp_path: Path) -> None:
    """If HEAD is missing, a subsequent init_repo call should recreate it."""
    dg = init_repo(tmp_path)
    head_path = dg / "HEAD"
    head_path.unlink()

    dg2 = init_repo(tmp_path)
    assert dg2 == dg
    assert head_path.is_file()
    assert head_path.read_text(encoding="utf-8").strip() == "ref: refs/heads/main"


def test_init_repairs_empty_index(tmp_path: Path) -> None:
    """If index is empty or missing, init_repo should recreate a valid binary index."""
    dg = init_repo(tmp_path)
    index_path = dg / "index"
    index_path.write_bytes(b"")

    dg2 = init_repo(tmp_path)
    assert dg2 == dg
    index = read_index(dg2)
    assert index.entries == {}


def test_status_handles_corrupted_index(tmp_path: Path) -> None:
    """Corrupted index should be treated as empty; status must not crash."""
    dg = init_repo(tmp_path)
    index_path = dg / "index"
    index_path.write_bytes(b"not a valid index payload")

    status = compute_status(tmp_path)
    # Fresh repo, so with a reset index we expect everything clean.
    assert status.staged_new == []
    assert status.modified == []
    assert status.untracked == []

