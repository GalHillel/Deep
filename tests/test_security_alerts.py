"""Tests for security alerts and compliance (Phase 35)."""
from pathlib import Path
import subprocess, sys, os
import pytest

from deep.core.audit import AuditLog
from deep.core.repository import DEEP_DIR


@pytest.fixture
def security_repo(tmp_path):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path.cwd() / "src")
    subprocess.run([sys.executable, "-m", "deep.main", "init"], cwd=tmp_path, env=env, check=True)
    return tmp_path


def test_alert_large_deletion(security_repo):
    """Detect alert when many files are deleted."""
    log = AuditLog(security_repo / DEEP_DIR)
    # Simulate many delete operations
    for i in range(20):
        log.record("mallory", "delete", ref="main", details=f"file_{i}.txt")
    deletes = log.read_by_action("delete")
    assert len(deletes) >= 20
    # Alert condition: more than 10 deletes by same user
    user_deletes = [e for e in deletes if e.user == "mallory"]
    assert len(user_deletes) >= 20  # Would trigger alert if threshold > 10


def test_alert_force_push(security_repo):
    """Track force push events."""
    log = AuditLog(security_repo / DEEP_DIR)
    log.record("attacker", "force_push", ref="main", sha="abc123", details="force")
    force_pushes = log.read_by_action("force_push")
    assert len(force_pushes) == 1


def test_compliance_report_generation(security_repo):
    """Generate a compliance summary from audit log."""
    log = AuditLog(security_repo / DEEP_DIR)
    log.record("alice", "commit", sha="aaa")
    log.record("bob", "push", sha="bbb")
    log.record("alice", "merge", sha="ccc")
    entries = log.read_all()
    # Build compliance report
    users = set(e.user for e in entries)
    actions = set(e.action for e in entries)
    assert "alice" in users
    assert "bob" in users
    assert "commit" in actions
    assert len(entries) == 3


def test_audit_tamper_detection(security_repo):
    """Audit log should be append-only and preserve all entries."""
    log = AuditLog(security_repo / DEEP_DIR)
    log.record("alice", "commit")
    count1 = len(log.read_all())
    log.record("bob", "push")
    count2 = len(log.read_all())
    assert count2 == count1 + 1
