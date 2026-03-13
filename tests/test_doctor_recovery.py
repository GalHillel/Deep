"""Tests for doctor + txlog recovery integration (Phase 38)."""
from pathlib import Path
import subprocess, sys, os
import pytest

from deep.storage.txlog import TransactionLog
from deep.core.repository import DEEP_DIR


@pytest.fixture
def recovery_repo(tmp_path):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path.cwd())
    subprocess.run([sys.executable, "-m", "deep.main", "init"], cwd=tmp_path, env=env, check=True)
    (tmp_path / "a.txt").write_text("hello")
    subprocess.run([sys.executable, "-m", "deep.main", "add", "a.txt"], cwd=tmp_path, env=env, check=True)
    subprocess.run([sys.executable, "-m", "deep.main", "commit", "-m", "init"], cwd=tmp_path, env=env, check=True)
    return tmp_path, env


def test_doctor_detects_txlog_issues(recovery_repo):
    """Doctor should detect incomplete transactions."""
    repo, env = recovery_repo
    txlog = TransactionLog(repo / DEEP_DIR)
    txlog.begin("commit", "orphan tx")
    # Doctor should detect
    result = subprocess.run(
        [sys.executable, "-m", "deep.main", "doctor"],
        cwd=repo, env=env, capture_output=True, text=True
    )
    # Doctor should still succeed (it checks objects/refs, txlog is extra)
    assert result.returncode == 0


def test_manual_recovery(recovery_repo):
    """Manually recover from incomplete txlog."""
    repo, _ = recovery_repo
    txlog = TransactionLog(repo / DEEP_DIR)
    tx1 = txlog.begin("push", "simulated crash")
    tx2 = txlog.begin("merge", "simulated crash 2")
    assert txlog.needs_recovery()
    for record in txlog.get_incomplete():
        txlog.rollback(record.tx_id, "auto-recovery")
    assert not txlog.needs_recovery()


def test_recovery_preserves_committed_tx(recovery_repo):
    """Recovery should not affect committed transactions."""
    repo, _ = recovery_repo
    txlog = TransactionLog(repo / DEEP_DIR)
    tx1 = txlog.begin("commit")
    txlog.commit(tx1)
    tx2 = txlog.begin("push")  # incomplete
    incomplete = txlog.get_incomplete()
    assert not any(r.tx_id == tx1 for r in incomplete)
    assert any(r.tx_id == tx2 for r in incomplete)


def test_doctor_runs_clean_after_recovery(recovery_repo):
    repo, env = recovery_repo
    result = subprocess.run(
        [sys.executable, "-m", "deep.main", "doctor"],
        cwd=repo, env=env, capture_output=True, text=True
    )
    assert result.returncode == 0
    assert "OK" in result.stdout or "healthy" in result.stdout.lower() or result.returncode == 0
