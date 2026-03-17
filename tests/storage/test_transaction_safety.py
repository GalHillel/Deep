"""
tests.test_transaction_safety
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Phase 8: Validate TXLog begin/commit/rollback, incomplete detection, and recovery.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from deep.storage.txlog import TransactionLog
from deep.core.repository import DEEP_DIR
from deep.cli.main import main


@pytest.fixture()
def repo(tmp_path: Path):
    os.chdir(tmp_path)
    main(["init"])
    return tmp_path


class TestTxLogBasics:
    def test_begin_commit(self, repo):
        txlog = TransactionLog(repo / DEEP_DIR)
        tx_id = txlog.begin("test-op", "details")
        assert tx_id
        txlog.commit(tx_id)
        records = txlog.read_all()
        statuses = {r.tx_id: r.status for r in records}
        assert statuses[tx_id] == "COMMIT"

    def test_begin_rollback(self, repo):
        txlog = TransactionLog(repo / DEEP_DIR)
        tx_id = txlog.begin("test-op", "will rollback")
        txlog.rollback(tx_id, "test reason")
        records = txlog.read_all()
        statuses = {r.tx_id: r.status for r in records}
        assert statuses[tx_id] == "ROLLBACK"

    def test_multiple_transactions(self, repo):
        txlog = TransactionLog(repo / DEEP_DIR)
        tx1 = txlog.begin("op1")
        tx2 = txlog.begin("op2")
        txlog.commit(tx1)
        txlog.rollback(tx2, "cancel")
        records = txlog.read_all()
        by_id = {r.tx_id: r for r in records}
        assert by_id[tx1].status == "COMMIT"
        assert by_id[tx2].status == "ROLLBACK"


class TestIncompleteDetection:
    def test_incomplete_transaction(self, repo):
        txlog = TransactionLog(repo / DEEP_DIR)
        tx_id = txlog.begin("incomplete-op", "left hanging")
        # Don't commit or rollback
        incomplete = txlog.get_incomplete()
        assert any(r.tx_id == tx_id for r in incomplete)
        assert txlog.needs_recovery()

    def test_no_incomplete_when_all_committed(self, repo):
        txlog = TransactionLog(repo / DEEP_DIR)
        tx = txlog.begin("done-op")
        txlog.commit(tx)
        assert not txlog.needs_recovery()


class TestRecovery:
    def test_recover_rolls_back_incomplete(self, repo):
        txlog = TransactionLog(repo / DEEP_DIR)
        tx_id = txlog.begin("crash-op", "simulated crash")
        # Simulate crash by not committing
        assert txlog.needs_recovery()
        txlog.recover()
        # After recovery, incomplete should be resolved
        assert not txlog.needs_recovery()


class TestAtomicWriter:
    def test_atomic_write_creates_file(self, repo):
        from deep.utils.utils import AtomicWriter
        target = repo / "atomic_test.txt"
        with AtomicWriter(target, mode="w") as aw:
            aw.write("test content")
        assert target.read_text() == "test content"

    def test_atomic_write_no_partial(self, repo):
        from deep.utils.utils import AtomicWriter
        target = repo / "atomic_fail.txt"
        try:
            with AtomicWriter(target, mode="w") as aw:
                aw.write("partial")
                raise RuntimeError("simulated crash")
        except RuntimeError:
            pass
        # File should not exist after failed write
        assert not target.exists()
