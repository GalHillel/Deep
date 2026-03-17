"""
tests.test_commit_crash
~~~~~~~~~~~~~~~~~~~~~~~

Crash simulation tests around the DeepBridge ``commit`` command and WAL.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest import mock

import pytest

from deep.commands.commit_cmd import run as commit_run
from deep.commands.add_cmd import run as add_run
from deep.core.repository import init_repo,DEEP_DIR
from deep.storage.txlog import TransactionLog


class Args:
    def __init__(self, message: str, ai: bool = False, sign: bool = False, allow_empty: bool = False):
        self.message = message
        self.ai = ai
        self.sign = sign
        self.allow_empty = allow_empty


def _basic_repo(tmp_path: Path) -> Path:
    """Create a repo with a single initial commit."""
    dg = init_repo(tmp_path)
    # Ensure add/commit operate inside this repo
    os.chdir(tmp_path)
    f = tmp_path / "f.txt"
    f.write_text("v1")
    add_run(type("A", (), {"files": [str(f)]})())
    commit_run(Args("first"))
    return dg


def test_crash_before_ref_update_leaves_orphan_but_no_wal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Crash after commit object is written but before WAL begin should not require recovery."""
    repo_root = tmp_path
    dg = _basic_repo(repo_root)

    # Stage a second change
    f = repo_root / "f.txt"
    f.write_text("v2")
    add_run(type("A", (), {"files": [str(f)]})())

    monkeypatch.setenv("DEEP_CRASH_TEST", "BEFORE_REF_UPDATE")

    with pytest.raises(RuntimeError, match="simulated crash before ref update"):
        commit_run(Args("second"))

    txlog = TransactionLog(dg)
    assert not txlog.needs_recovery()


def test_crash_after_wal_begin_recovers_forward(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Crash after WAL begin but before ref update should be recovered by TransactionLog."""
    repo_root = tmp_path
    dg = _basic_repo(repo_root)

    # Stage a second change
    f = repo_root / "g.txt"
    f.write_text("v2")
    add_run(type("A", (), {"files": [str(f)]})())

    monkeypatch.setenv("DEEP_CRASH_TEST", "AFTER_BEGIN_BEFORE_REF")

    with pytest.raises(RuntimeError, match="simulated crash after WAL begin"):
        commit_run(Args("second"))

    txlog = TransactionLog(dg)
    assert txlog.needs_recovery()

    from deep.core.refs import resolve_head
    before_recover = resolve_head(dg)

    txlog.recover()

    after_recover = resolve_head(dg)
    assert not txlog.needs_recovery()
    # HEAD should now point to a different commit after recovery.
    assert before_recover != after_recover

