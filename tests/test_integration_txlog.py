"""Tests for txlog/telemetry integration in core commands (Phase 31)."""
from pathlib import Path
import subprocess, sys, os, json
import pytest

from deep.core.repository import DEEP_DIR


@pytest.fixture
def integrated_repo(tmp_path):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path.cwd() / "src")
    subprocess.run([sys.executable, "-m", "deep.cli.main", "init"], cwd=tmp_path, env=env, check=True)
    (tmp_path / "a.txt").write_text("hello")
    subprocess.run([sys.executable, "-m", "deep.cli.main", "add", "a.txt"], cwd=tmp_path, env=env, check=True)
    subprocess.run([sys.executable, "-m", "deep.cli.main", "commit", "-m", "initial"], cwd=tmp_path, env=env, check=True)
    return tmp_path, env


def test_commit_creates_txlog(integrated_repo):
    repo, env = integrated_repo
    txlog = repo / DEEP_DIR / "txlog"
    assert txlog.exists()
    content = txlog.read_text()
    assert '"commit"' in content
    assert '"COMMIT"' in content


def test_commit_creates_telemetry(integrated_repo):
    repo, env = integrated_repo
    metrics = repo / DEEP_DIR / "metrics.json"
    assert metrics.exists()
    data = json.loads(metrics.read_text())
    assert "counters" in data
    assert data["counters"].get("commit", 0) >= 1


def test_commit_creates_audit_log(integrated_repo):
    repo, env = integrated_repo
    audit = repo / DEEP_DIR / "audit.log"
    assert audit.exists()
    content = audit.read_text()
    assert '"commit"' in content


def test_multiple_commits_tracked(integrated_repo):
    repo, env = integrated_repo
    for i in range(3):
        (repo / f"file_{i}.txt").write_text(f"v{i}")
        subprocess.run([sys.executable, "-m", "deep.cli.main", "add", f"file_{i}.txt"], cwd=repo, env=env, check=True)
        subprocess.run([sys.executable, "-m", "deep.cli.main", "commit", "-m", f"commit {i}"], cwd=repo, env=env, check=True)

    metrics = json.loads((repo / DEEP_DIR / "metrics.json").read_text())
    assert metrics["counters"]["commit"] >= 4  # initial + 3 more

    from deep.storage.txlog import TransactionLog
    txlog = TransactionLog(repo / DEEP_DIR)
    assert not txlog.needs_recovery()


def test_merge_creates_txlog_and_audit(integrated_repo):
    repo, env = integrated_repo
    # Create a branch and commit
    subprocess.run([sys.executable, "-m", "deep.cli.main", "branch", "feature"], cwd=repo, env=env, check=True)
    subprocess.run([sys.executable, "-m", "deep.cli.main", "checkout", "feature"], cwd=repo, env=env, check=True)
    (repo / "b.txt").write_text("feature")
    subprocess.run([sys.executable, "-m", "deep.cli.main", "add", "b.txt"], cwd=repo, env=env, check=True)
    subprocess.run([sys.executable, "-m", "deep.cli.main", "commit", "-m", "feature commit"], cwd=repo, env=env, check=True)
    subprocess.run([sys.executable, "-m", "deep.cli.main", "checkout", "main"], cwd=repo, env=env, check=True)
    subprocess.run([sys.executable, "-m", "deep.cli.main", "merge", "feature"], cwd=repo, env=env, check=True)

    txlog_content = (repo / DEEP_DIR / "txlog").read_text()
    assert '"merge"' in txlog_content

    audit_content = (repo / DEEP_DIR / "audit.log").read_text()
    assert '"merge"' in audit_content
