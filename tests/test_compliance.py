"""Tests for security and compliance (Phase 47)."""
from pathlib import Path
import subprocess, sys, os, json
import pytest

from deep_git.core.repository import DEEP_GIT_DIR


@pytest.fixture
def compliance_repo(tmp_path):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path.cwd())
    subprocess.run([sys.executable, "-m", "deep_git.main", "init"], cwd=tmp_path, env=env, check=True)
    return tmp_path, env


def test_signed_commit(compliance_repo):
    repo, env = compliance_repo
    (repo / "f.txt").write_text("content")
    subprocess.run([sys.executable, "-m", "deep_git.main", "add", "f.txt"], cwd=repo, env=env, check=True)
    
    # Commit with --sign
    subprocess.run([sys.executable, "-m", "deep_git.main", "commit", "-m", "signed", "--sign"], cwd=repo, env=env, check=True)
    
    # Verify signature in raw object
    from deep_git.core.refs import resolve_head
    from deep_git.core.objects import read_object, Commit
    sha = resolve_head(repo / DEEP_GIT_DIR)
    obj = read_object(repo / DEEP_GIT_DIR / "objects", sha)
    assert isinstance(obj, Commit)
    assert obj.signature is not None
    assert obj.signature.startswith("SIG:") or obj.signature == "MOCKED_GPG_SIGNATURE"


def test_audit_log_cli(compliance_repo):
    repo, env = compliance_repo
    # Perform an action that logs (commit)
    (repo / "f.txt").write_text("content")
    subprocess.run([sys.executable, "-m", "deep_git.main", "add", "f.txt"], cwd=repo, env=env, check=True)
    subprocess.run([sys.executable, "-m", "deep_git.main", "commit", "-m", "c1"], cwd=repo, env=env, check=True)
    
    result = subprocess.run(
        [sys.executable, "-m", "deep_git.main", "audit"],
        cwd=repo, env=env, capture_output=True, text=True, check=True
    )
    assert "TIMESTAMP" in result.stdout
    assert "commit" in result.stdout


def test_rbac_check(compliance_repo):
    from deep_git.core.auth import AuthManager
    repo, env = compliance_repo
    dg_dir = repo / DEEP_GIT_DIR
    
    auth = AuthManager(dg_dir)
    auth.add_user("admin_user", "admin")
    auth.add_user("read_user", "read")
    
    assert auth.check_permission("admin_user", "push") is True
    assert auth.check_permission("read_user", "push") is False
    assert auth.check_permission("read_user", "read") is True
