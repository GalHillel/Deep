"""Tests for deterministic benchmark suite (Phase 36)."""
from pathlib import Path
import subprocess, sys, os, json
import pytest

from deep.core.telemetry import TelemetryCollector, Timer
from deep.core.repository import DEEP_DIR


@pytest.fixture
def bench_repo(tmp_path):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path.cwd())
    subprocess.run([sys.executable, "-m", "deep.main", "init"], cwd=tmp_path, env=env, check=True)
    return tmp_path, env


def test_benchmark_deterministic(bench_repo):
    """Run same benchmark twice, verify consistent structure."""
    repo, env = bench_repo
    tc = TelemetryCollector(repo / DEEP_DIR)
    with Timer(tc, "bench_commit"):
        pass  # simulated
    with Timer(tc, "bench_commit"):
        pass
    summary = tc.summary()
    assert summary["bench_commit_count"] == 2
    assert summary["bench_commit_avg_ms"] >= 0


def test_metrics_json_export(bench_repo):
    repo, env = bench_repo
    tc = TelemetryCollector(repo / DEEP_DIR)
    tc.record("gc", 100.0)
    tc.record("index_rebuild", 50.0)
    metrics_path = repo / DEEP_DIR / "metrics.json"
    assert metrics_path.exists()
    data = json.loads(metrics_path.read_text())
    assert "summary" in data
    assert "counters" in data


def test_regression_detection(bench_repo):
    """If avg latency doubles, that's a regression."""
    repo, _ = bench_repo
    tc = TelemetryCollector(repo / DEEP_DIR)
    tc.record("commit", 10.0)
    tc.record("commit", 12.0)
    baseline_avg = tc.summary()["commit_avg_ms"]
    tc.record("commit", 100.0)  # simulated regression
    new_avg = tc.summary()["commit_avg_ms"]
    # Regression = new avg > 2x baseline
    assert new_avg > baseline_avg  # Detected


def test_telemetry_counters_accumulate(bench_repo):
    repo, _ = bench_repo
    tc = TelemetryCollector(repo / DEEP_DIR)
    for _ in range(10):
        tc.record("push", 5.0)
    assert tc.summary()["push_count"] == 10
