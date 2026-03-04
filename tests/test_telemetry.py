"""Tests for telemetry and performance metrics (Phase 28)."""
from pathlib import Path
import subprocess, sys, os, time
import pytest

from deep_git.core.telemetry import TelemetryCollector, Timer
from deep_git.core.repository import DEEP_GIT_DIR


@pytest.fixture
def telem_repo(tmp_path):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path.cwd())
    subprocess.run([sys.executable, "-m", "deep_git.main", "init"], cwd=tmp_path, env=env, check=True)
    return tmp_path


def test_telemetry_record(telem_repo):
    tc = TelemetryCollector(telem_repo / DEEP_GIT_DIR)
    tc.record("commit", 12.5, "test commit")
    tc.record("commit", 8.3)
    tc.record("push", 45.0)
    summary = tc.summary()
    assert summary["total_ops"] == 3
    assert summary["commit_count"] == 2
    assert summary["push_count"] == 1


def test_telemetry_timer(telem_repo):
    tc = TelemetryCollector(telem_repo / DEEP_GIT_DIR)
    with Timer(tc, "sleep"):
        time.sleep(0.01)
    summary = tc.summary()
    assert summary["total_ops"] == 1
    assert summary["sleep_avg_ms"] >= 5  # at least 5ms


def test_telemetry_persistence(telem_repo):
    dg_dir = telem_repo / DEEP_GIT_DIR
    tc1 = TelemetryCollector(dg_dir)
    tc1.record("gc", 100.0)
    # Check file exists
    assert (dg_dir / "metrics.json").exists()


def test_telemetry_export(telem_repo):
    tc = TelemetryCollector(telem_repo / DEEP_GIT_DIR)
    tc.record("fetch", 50.0)
    export = tc.get_export()
    assert "counters" in export
    assert "summary" in export
    assert export["counters"]["fetch"] == 1
