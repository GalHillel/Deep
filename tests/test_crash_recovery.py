"""Tests for crash recovery and transaction log (Phase 27)."""
from pathlib import Path
import subprocess, sys, os
import pytest

from deep.storage.txlog import TransactionLog
from deep.core.repository import DEEP_DIR


@pytest.fixture
def tx_repo(tmp_path):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path.cwd() / "src")
    subprocess.run([sys.executable, "-m", "deep.main", "init"], cwd=tmp_path, env=env, check=True)
    return tmp_path


def test_txlog_begin_commit(tx_repo):
    txlog = TransactionLog(tx_repo / DEEP_DIR)
    tx_id = txlog.begin("commit", "test commit")
    assert tx_id.startswith("commit_")
    assert txlog.needs_recovery()
    txlog.commit(tx_id)
    assert not txlog.needs_recovery()


def test_txlog_begin_rollback(tx_repo):
    txlog = TransactionLog(tx_repo / DEEP_DIR)
    tx_id = txlog.begin("push")
    txlog.rollback(tx_id, "network error")
    assert not txlog.needs_recovery()


def test_txlog_incomplete_detection(tx_repo):
    txlog = TransactionLog(tx_repo / DEEP_DIR)
    tx1 = txlog.begin("commit")
    tx2 = txlog.begin("push")
    txlog.commit(tx1)
    incomplete = txlog.get_incomplete()
    assert any(r.tx_id == tx2 for r in incomplete)
    assert not any(r.tx_id == tx1 for r in incomplete)


def test_txlog_persistence(tx_repo):
    dg_dir = tx_repo / DEEP_DIR
    txlog1 = TransactionLog(dg_dir)
    tx_id = txlog1.begin("merge")
    # Reload from disk
    txlog2 = TransactionLog(dg_dir)
    assert txlog2.needs_recovery()
    txlog2.commit(tx_id)
    txlog3 = TransactionLog(dg_dir)
    assert not txlog3.needs_recovery()


def test_simulated_crash_recovery(tx_repo):
    """Simulate crash: begin tx but don't commit. Verify recovery detects it."""
    txlog = TransactionLog(tx_repo / DEEP_DIR)
    tx_id = txlog.begin("commit", "crash simulation")
    # Simulate crash — no commit/rollback
    # Reload
    txlog2 = TransactionLog(tx_repo / DEEP_DIR)
    assert txlog2.needs_recovery()
    incomplete = txlog2.get_incomplete()
    assert len(incomplete) == 1
    # Recovery: rollback incomplete
    for record in incomplete:
        txlog2.rollback(record.tx_id, "auto-recovery")
    assert not txlog2.needs_recovery()
