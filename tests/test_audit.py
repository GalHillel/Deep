"""Tests for enterprise security and audit logging (Phase 25)."""
from pathlib import Path
import subprocess, sys, os
import pytest

from deep_git.core.audit import AuditLog
from deep_git.core.auth import AuthManager
from deep_git.core.repository import DEEP_GIT_DIR


@pytest.fixture
def enterprise_repo(tmp_path):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path.cwd())
    subprocess.run([sys.executable, "-m", "deep_git.main", "init"], cwd=tmp_path, env=env, check=True)
    return tmp_path


# ── Audit Log Tests ──
def test_audit_record_and_read(enterprise_repo):
    log = AuditLog(enterprise_repo / DEEP_GIT_DIR)
    log.record("alice", "commit", ref="refs/heads/main", sha="abc123")
    log.record("bob", "push", ref="refs/heads/main", sha="def456")
    entries = log.read_all()
    assert len(entries) == 2
    assert entries[0].user == "alice"
    assert entries[1].action == "push"


def test_audit_filter_by_user(enterprise_repo):
    log = AuditLog(enterprise_repo / DEEP_GIT_DIR)
    log.record("alice", "commit")
    log.record("bob", "push")
    log.record("alice", "merge")
    assert len(log.read_by_user("alice")) == 2


def test_audit_filter_by_action(enterprise_repo):
    log = AuditLog(enterprise_repo / DEEP_GIT_DIR)
    log.record("alice", "commit")
    log.record("bob", "commit")
    log.record("alice", "push")
    assert len(log.read_by_action("commit")) == 2


# ── Auth Tests ──
def test_auth_add_and_get_user(enterprise_repo):
    auth = AuthManager(enterprise_repo / DEEP_GIT_DIR)
    auth.add_user("alice", "admin")
    auth.add_user("bob", "write")
    auth.add_user("charlie", "read")
    assert auth.get_user("alice").role == "admin"
    assert auth.get_user("bob").role == "write"


def test_auth_admin_can_do_everything(enterprise_repo):
    auth = AuthManager(enterprise_repo / DEEP_GIT_DIR)
    auth.add_user("admin", "admin")
    assert auth.check_permission("admin", "push", "main") is True
    assert auth.check_permission("admin", "delete_branch", "main") is True
    assert auth.check_permission("admin", "read") is True


def test_auth_read_user_cannot_push(enterprise_repo):
    auth = AuthManager(enterprise_repo / DEEP_GIT_DIR)
    auth.add_user("reader", "read")
    assert auth.check_permission("reader", "push", "main") is False
    assert auth.check_permission("reader", "fetch") is True


def test_auth_write_user_branch_restriction(enterprise_repo):
    auth = AuthManager(enterprise_repo / DEEP_GIT_DIR)
    auth.add_user("dev", "write", branches=["feature"])
    assert auth.check_permission("dev", "push", "feature") is True
    assert auth.check_permission("dev", "push", "main") is False


def test_auth_persistence(enterprise_repo):
    dg_dir = enterprise_repo / DEEP_GIT_DIR
    auth1 = AuthManager(dg_dir)
    auth1.add_user("alice", "admin")
    # Reload from disk
    auth2 = AuthManager(dg_dir)
    assert auth2.get_user("alice").role == "admin"


def test_auth_unknown_user(enterprise_repo):
    auth = AuthManager(enterprise_repo / DEEP_GIT_DIR)
    assert auth.check_permission("unknown", "read") is False
