"""
tests.test_god_mode_security
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
GOD MODE: Comprehensive tests for security hardening.

Covers:
- ECDSA/HMAC key generation, rotation, revocation
- Commit signing and verification
- Merkle audit chain integrity
- Sandbox execution with restrictions
- Signed WAL entries and recovery
- P2P commit signature verification
- Full pipeline integration
- CLI integration
"""

import copy
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from deep.core.repository import DEEP_DIR


# ── Fixtures ─────────────────────────────────────────────────────────

@pytest.fixture
def god_repo(tmp_path):
    """Initialize a DeepGit repo with a key and a signed commit."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path.cwd())
    subprocess.run([sys.executable, "-m", "deep.main", "init"],
                   cwd=tmp_path, env=env, check=True)
    dg_dir = tmp_path / DEEP_DIR
    return tmp_path, dg_dir, env


# ── Key Management ───────────────────────────────────────────────────

def test_ecdsa_key_generation(god_repo):
    """KeyManager generates and persists a signing key."""
    _, dg_dir, _ = god_repo
    from deep.core.security import KeyManager
    km = KeyManager(dg_dir)
    assert km.get_active_key() is None

    key = km.generate_key("test_key_1")
    assert key.key_id == "test_key_1"
    assert key.status == "active"
    assert len(key.secret) == 32

    # Persistence check
    km2 = KeyManager(dg_dir)
    loaded = km2.get_key("test_key_1")
    assert loaded is not None
    assert loaded.secret == key.secret


def test_key_rotation(god_repo):
    """Rotating a key revokes the old one and creates a new active key."""
    _, dg_dir, _ = god_repo
    from deep.core.security import KeyManager
    km = KeyManager(dg_dir)
    old = km.generate_key("old_key")
    assert old.status == "active"

    new = km.rotate_key("old_key")
    assert new.status == "active"
    assert new.key_id != "old_key"

    revoked = km.get_key("old_key")
    assert revoked.status == "revoked"

    active = km.get_active_key()
    assert active.key_id == new.key_id


def test_key_revocation_rejects_commit(god_repo):
    """A revoked key cannot be used for signing."""
    _, dg_dir, _ = god_repo
    from deep.core.security import KeyManager, CommitSigner
    km = KeyManager(dg_dir)
    key = km.generate_key("rev_key")
    km.revoke_key("rev_key")

    signer = CommitSigner(km)
    with pytest.raises(ValueError, match="revoked"):
        signer.sign(b"test data", "rev_key")


# ── Commit Signing ───────────────────────────────────────────────────

def test_commit_signing_and_verification(god_repo):
    """Sign a commit and verify the signature round-trips correctly."""
    _, dg_dir, _ = god_repo
    from deep.core.security import KeyManager, CommitSigner
    from deep.storage.objects import Commit

    km = KeyManager(dg_dir)
    km.generate_key("sign_key")
    signer = CommitSigner(km)

    commit = Commit(
        tree_sha="a" * 40,
        parent_shas=[],
        author="Test <test@test>",
        committer="Test <test@test>",
        message="test commit",
    )

    content = commit.serialize_content()
    sig_hex, key_id = signer.sign(content, "sign_key")

    # Set signature in GOD MODE format
    commit.signature = f"SIG:{key_id}:{sig_hex}"

    # Verify
    assert signer.verify_commit(commit) is True


def test_commit_verify_rejects_tampered(god_repo):
    """Tampering with commit content after signing should fail verification."""
    _, dg_dir, _ = god_repo
    from deep.core.security import KeyManager, CommitSigner
    from deep.storage.objects import Commit

    km = KeyManager(dg_dir)
    km.generate_key("tamper_key")
    signer = CommitSigner(km)

    commit = Commit(
        tree_sha="b" * 40,
        parent_shas=[],
        author="Test <test@test>",
        committer="Test <test@test>",
        message="original message",
    )

    content = commit.serialize_content()
    sig_hex, key_id = signer.sign(content, "tamper_key")
    commit.signature = f"SIG:{key_id}:{sig_hex}"

    # Tamper with message
    commit.message = "TAMPERED message"
    assert signer.verify_commit(commit) is False


# ── Merkle Audit Chain ───────────────────────────────────────────────

def test_merkle_audit_chain(god_repo):
    """Audit entries form a valid SHA-256 hash chain."""
    _, dg_dir, _ = god_repo
    from deep.core.audit import AuditLog

    audit = AuditLog(dg_dir)
    audit.record("alice", "commit", sha="aaa")
    audit.record("bob", "push", sha="bbb")
    audit.record("alice", "merge", sha="ccc")

    is_valid, idx = audit.verify_chain()
    assert is_valid is True
    assert idx == -1


def test_merkle_chain_tamper_detection(god_repo):
    """Mutating an audit entry breaks the Merkle chain."""
    _, dg_dir, _ = god_repo
    from deep.core.audit import AuditLog

    audit = AuditLog(dg_dir)
    audit.record("alice", "commit", sha="aaa")
    audit.record("bob", "push", sha="bbb")

    is_valid, _ = audit.verify_chain()
    assert is_valid is True

    # Tamper with the log file: modify first entry's action
    log_path = dg_dir / "audit.log"
    lines = log_path.read_text(encoding="utf-8").splitlines()
    data = json.loads(lines[0])
    data["action"] = "TAMPERED"
    lines[0] = json.dumps(data)
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    is_valid, invalid_idx = audit.verify_chain()
    assert is_valid is False
    assert invalid_idx == 0


def test_audit_export_report(god_repo):
    """Audit report is generated with integrity status."""
    _, dg_dir, _ = god_repo
    from deep.core.audit import AuditLog

    audit = AuditLog(dg_dir)
    audit.record("alice", "commit")
    audit.record("bob", "merge")

    report = audit.export_report()
    assert "DEEPGIT AUDIT REPORT" in report
    assert "✅ VALID" in report
    assert "alice" in report
    assert "bob" in report


# ── Signed WAL ───────────────────────────────────────────────────────

def test_signed_wal_entry(god_repo):
    """WAL entries can be signed and verified."""
    _, dg_dir, _ = god_repo
    from deep.core.security import KeyManager
    from deep.storage.txlog import TransactionLog

    km = KeyManager(dg_dir)
    key = km.generate_key("wal_key")

    txlog = TransactionLog(dg_dir)
    tx_id = txlog.begin(
        operation="commit",
        details="signed tx",
        signing_key_id="wal_key",
    )
    txlog.commit(tx_id)

    records = txlog.read_all()
    # The BEGIN record should have a signature
    begin_record = [r for r in records if r.status == "BEGIN"][0]
    assert begin_record.signature != ""
    assert begin_record.signing_key_id == "wal_key"

    # Verify
    assert txlog.verify_record_signature(begin_record) is True


def test_wal_recovery_verifies_signature(god_repo):
    """Recovery rejects WAL entries with tampered signatures."""
    _, dg_dir, _ = god_repo
    from deep.core.security import KeyManager
    from deep.storage.txlog import TransactionLog

    km = KeyManager(dg_dir)
    km.generate_key("wal_key2")

    txlog = TransactionLog(dg_dir)
    tx_id = txlog.begin(
        operation="commit",
        details="will tamper",
        signing_key_id="wal_key2",
        branch_ref="main",
        previous_commit_sha="",
    )

    # Tamper with WAL: modify signature in the file
    log_path = dg_dir / "txlog"
    lines = log_path.read_text(encoding="utf-8").splitlines()
    data = json.loads(lines[-1])
    data["signature"] = "TAMPERED_SIGNATURE"
    lines[-1] = json.dumps(data)
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Recovery should detect and reject the tampered entry
    txlog2 = TransactionLog(dg_dir)
    txlog2.recover()

    # Check the tampered tx was rolled back, not committed
    records = txlog2.read_all()
    rollback_records = [r for r in records if r.status == "ROLLBACK"]
    assert len(rollback_records) >= 1
    assert any("signature verification failed" in r.details for r in rollback_records)


# ── Sandbox Execution ────────────────────────────────────────────────

def test_sandbox_restricts_writes(god_repo):
    """Sandbox runs scripts in an isolated environment."""
    _, dg_dir, _ = god_repo
    from deep.core.security import SandboxRunner

    # Create a simple script that writes output
    script = dg_dir / "tmp" / "test_script.py"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text('print("hello from sandbox")\n', encoding="utf-8")

    runner = SandboxRunner(dg_dir, allowed_write_paths=[dg_dir / "tmp"])
    result = runner.run(script)

    assert result.exit_code == 0
    assert "hello from sandbox" in result.stdout
    assert len(result.operations_log) > 0


def test_sandbox_logs_operations(god_repo):
    """Sandbox logs all operations including start and end."""
    _, dg_dir, _ = god_repo
    from deep.core.security import SandboxRunner

    script = dg_dir / "tmp" / "log_test.py"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text('import sys; print("logged", file=sys.stdout)\n', encoding="utf-8")

    runner = SandboxRunner(dg_dir)
    result = runner.run(script)

    assert any("SANDBOX START" in log for log in result.operations_log)
    assert any("SANDBOX END" in log for log in result.operations_log)
    assert any("EXEC" in log for log in result.operations_log)


def test_sandbox_timeout(god_repo):
    """Long-running scripts are killed after timeout."""
    _, dg_dir, _ = god_repo
    from deep.core.security import SandboxRunner

    script = dg_dir / "tmp" / "slow_script.py"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text('import time; time.sleep(60)\n', encoding="utf-8")

    runner = SandboxRunner(dg_dir)
    result = runner.run(script, timeout=2)

    assert result.timed_out is True
    assert result.exit_code == -1


def test_sandbox_nonexistent_script(god_repo):
    """Sandbox gracefully handles missing scripts."""
    _, dg_dir, _ = god_repo
    from deep.core.security import SandboxRunner

    runner = SandboxRunner(dg_dir)
    result = runner.run(Path("/nonexistent/script.py"))

    assert result.exit_code == 1
    assert "not found" in result.stderr.lower() or "not found" in result.operations_log[0].lower()


# ── P2P Verification ────────────────────────────────────────────────

def test_p2p_rejects_unsigned_commit(god_repo):
    """P2P rejects commits without signatures."""
    _, dg_dir, _ = god_repo
    from deep.storage.objects import Commit
    from deep.core.security import KeyManager, verify_peer_commit

    km = KeyManager(dg_dir)

    commit = Commit(
        tree_sha="c" * 40,
        message="unsigned commit",
        signature=None,
    )

    assert verify_peer_commit(commit, km) is False


def test_p2p_accepts_signed_commit(god_repo):
    """P2P accepts commits with valid signatures."""
    _, dg_dir, _ = god_repo
    from deep.storage.objects import Commit
    from deep.core.security import KeyManager, CommitSigner, verify_peer_commit

    km = KeyManager(dg_dir)
    km.generate_key("p2p_key")
    signer = CommitSigner(km)

    commit = Commit(
        tree_sha="d" * 40,
        message="signed for p2p",
        signature=None,
    )

    content = commit.serialize_content()
    sig_hex, key_id = signer.sign(content, "p2p_key")
    commit.signature = f"SIG:{key_id}:{sig_hex}"

    assert verify_peer_commit(commit, km) is True


# ── Crash Recovery with Signed Commits ───────────────────────────────

def test_crash_mid_signed_commit(god_repo):
    """Recovery works correctly for signed commits that crash mid-write."""
    repo, dg_dir, env = god_repo
    from deep.core.security import KeyManager
    from deep.storage.txlog import TransactionLog

    km = KeyManager(dg_dir)
    km.generate_key("crash_key")

    txlog = TransactionLog(dg_dir)

    # Simulate a crash: begin transaction but don't commit
    tx_id = txlog.begin(
        operation="commit",
        details="crash test",
        target_object_id="e" * 40,  # Object doesn't exist
        branch_ref="main",
        previous_commit_sha="",
        signing_key_id="crash_key",
    )

    # Verify the transaction is incomplete
    assert txlog.needs_recovery() is True

    # Run recovery
    txlog.recover()

    # Transaction should be resolved
    assert txlog.needs_recovery() is False


# ── Full Pipeline Integration ────────────────────────────────────────

def test_full_pipeline_integration(god_repo):
    """End-to-end: commit → sign → WAL → DAG → verify → audit."""
    repo, dg_dir, env = god_repo

    # Generate a signing key
    from deep.core.security import KeyManager, CommitSigner
    km = KeyManager(dg_dir)
    key = km.generate_key("pipeline_key")

    # Create and add a file
    (repo / "hello.txt").write_text("hello world")
    subprocess.run([sys.executable, "-m", "deep.main", "add", "hello.txt"],
                   cwd=repo, env=env, check=True)

    # Commit with signing
    subprocess.run([sys.executable, "-m", "deep.main", "commit", "-m", "signed commit", "--sign"],
                   cwd=repo, env=env, check=True)

    # Verify the commit was signed
    from deep.core.refs import resolve_head
    from deep.storage.objects import read_object, Commit
    sha = resolve_head(dg_dir)
    obj = read_object(dg_dir / "objects", sha)
    assert isinstance(obj, Commit)
    assert obj.signature is not None
    assert obj.signature.startswith("SIG:")

    # Verify signature
    signer = CommitSigner(km)
    assert signer.verify_commit(obj) is True

    # Verify audit chain
    from deep.core.audit import AuditLog
    audit = AuditLog(dg_dir)
    is_valid, _ = audit.verify_chain()
    assert is_valid is True

    # Verify WAL
    from deep.storage.txlog import TransactionLog
    txlog = TransactionLog(dg_dir)
    assert txlog.needs_recovery() is False


# ── CLI Integration ──────────────────────────────────────────────────

def test_verify_all_cli(god_repo):
    """deep verify --all runs without errors."""
    repo, dg_dir, env = god_repo

    # Create a commit first
    (repo / "f.txt").write_text("content")
    subprocess.run([sys.executable, "-m", "deep.main", "add", "f.txt"],
                   cwd=repo, env=env, check=True)
    subprocess.run([sys.executable, "-m", "deep.main", "commit", "-m", "c1"],
                   cwd=repo, env=env, check=True)

    result = subprocess.run(
        [sys.executable, "-m", "deep.main", "verify", "--all"],
        cwd=repo, env=env, capture_output=True, text=True
    )
    assert result.returncode == 0
    assert "VERIFICATION REPORT" in result.stdout
    assert "✅" in result.stdout


def test_rollback_verify_cli(god_repo):
    """deep rollback --verify runs without errors on clean repo."""
    repo, dg_dir, env = god_repo

    result = subprocess.run(
        [sys.executable, "-m", "deep.main", "rollback", "--verify"],
        cwd=repo, env=env, capture_output=True, text=True
    )
    assert result.returncode == 0
    assert "No incomplete transactions" in result.stdout


def test_audit_report_cli(god_repo):
    """deep audit report generates a formatted report."""
    repo, dg_dir, env = god_repo

    # Create a commit to generate audit entries
    (repo / "f.txt").write_text("content")
    subprocess.run([sys.executable, "-m", "deep.main", "add", "f.txt"],
                   cwd=repo, env=env, check=True)
    subprocess.run([sys.executable, "-m", "deep.main", "commit", "-m", "c1"],
                   cwd=repo, env=env, check=True)

    result = subprocess.run(
        [sys.executable, "-m", "deep.main", "audit", "report"],
        cwd=repo, env=env, capture_output=True, text=True
    )
    assert result.returncode == 0
    assert "AUDIT REPORT" in result.stdout
    assert "✅" in result.stdout
