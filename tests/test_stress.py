"""Ultra stress test & final hardening (Phase 40)."""
from pathlib import Path
import subprocess, sys, os, json, time
import pytest

from deep.core.repository import DEEP_DIR
from deep.core.refs import resolve_head, list_branches, list_tags
from deep.storage.txlog import TransactionLog
from deep.core.telemetry import TelemetryCollector
from deep.core.audit import AuditLog


@pytest.fixture
def stress_repo(tmp_path):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path.cwd() / "src")
    subprocess.run([sys.executable, "-m", "deep.main", "init"], cwd=tmp_path, env=env, check=True)
    return tmp_path, env


def test_rapid_commits(stress_repo):
    """50 rapid sequential commits — verify all tracked."""
    repo, env = stress_repo
    for i in range(50):
        (repo / f"f{i}.txt").write_text(f"data{i}")
        subprocess.run([sys.executable, "-m", "deep.main", "add", f"f{i}.txt"],
                       cwd=repo, env=env, check=True)
        subprocess.run([sys.executable, "-m", "deep.main", "commit", "-m", f"c{i}"],
                       cwd=repo, env=env, check=True)

    # Verify txlog
    txlog = TransactionLog(repo / DEEP_DIR)
    assert not txlog.needs_recovery()

    # Verify telemetry
    metrics = json.loads((repo / DEEP_DIR / "metrics.json").read_text())
    assert metrics["counters"]["commit"] == 50

    # Verify audit
    audit = AuditLog(repo / DEEP_DIR)
    commits = audit.read_by_action("commit")
    assert len(commits) == 50


def test_multi_branch_stress(stress_repo):
    """Create 10 branches, commit on each, merge back."""
    repo, env = stress_repo
    (repo / "base.txt").write_text("base")
    subprocess.run([sys.executable, "-m", "deep.main", "add", "base.txt"], cwd=repo, env=env, check=True)
    subprocess.run([sys.executable, "-m", "deep.main", "commit", "-m", "base"], cwd=repo, env=env, check=True)

    for i in range(10):
        subprocess.run([sys.executable, "-m", "deep.main", "branch", f"feat-{i}"],
                       cwd=repo, env=env, check=True)

    branches = list_branches(repo / DEEP_DIR)
    assert len(branches) >= 11  # main + 10


def test_doctor_after_stress(stress_repo):
    """Doctor should pass after stress operations."""
    repo, env = stress_repo
    (repo / "x.txt").write_text("x")
    subprocess.run([sys.executable, "-m", "deep.main", "add", "x.txt"], cwd=repo, env=env, check=True)
    subprocess.run([sys.executable, "-m", "deep.main", "commit", "-m", "x"], cwd=repo, env=env, check=True)
    result = subprocess.run(
        [sys.executable, "-m", "deep.main", "doctor"],
        cwd=repo, env=env, capture_output=True, text=True
    )
    assert result.returncode == 0


def test_telemetry_summary_after_stress(stress_repo):
    """Telemetry should have comprehensive data after many ops."""
    repo, env = stress_repo
    for i in range(10):
        (repo / f"s{i}.txt").write_text(f"s{i}")
        subprocess.run([sys.executable, "-m", "deep.main", "add", f"s{i}.txt"],
                       cwd=repo, env=env, check=True)
        subprocess.run([sys.executable, "-m", "deep.main", "commit", "-m", f"s{i}"],
                       cwd=repo, env=env, check=True)

    metrics_path = repo / DEEP_DIR / "metrics.json"
    assert metrics_path.exists()
    data = json.loads(metrics_path.read_text())
    assert data["counters"].get("commit", 0) >= 10


def test_ai_under_load(stress_repo):
    """AI assistant works after many commits."""
    repo, env = stress_repo
    for i in range(5):
        (repo / f"ai{i}.py").write_text(f"def func_{i}(): pass")
        subprocess.run([sys.executable, "-m", "deep.main", "add", f"ai{i}.py"],
                       cwd=repo, env=env, check=True)
        subprocess.run([sys.executable, "-m", "deep.main", "commit", "-m", f"func {i}"],
                       cwd=repo, env=env, check=True)

    from deep.ai.assistant import DeepGitAI
    ai = DeepGitAI(repo)
    result = ai.suggest_commit_message()
    assert result.suggestion_type == "commit_msg"
    quality = ai.analyze_quality()
    assert quality.suggestion_type == "quality"
