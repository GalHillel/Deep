"""Tests for CI/CD pipelines (Phase 42)."""
from pathlib import Path
import subprocess, sys, os, json
import pytest

from deep.core.repository import DEEP_DIR
from deep.core.pipeline import PipelineRunner, PipelineRun, PipelineJob


@pytest.fixture
def pipeline_repo(tmp_path):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path.cwd() / "src")
    subprocess.run([sys.executable, "-m", "deep.main", "init"], cwd=tmp_path, env=env, check=True)
    
    # Create an initial commit
    (tmp_path / "a.txt").write_text("hello")
    subprocess.run([sys.executable, "-m", "deep.main", "add", "a.txt"], cwd=tmp_path, env=env, check=True)
    subprocess.run([sys.executable, "-m", "deep.main", "commit", "-m", "initial"], cwd=tmp_path, env=env, check=True)
    
    # Create pipeline config
    config = [
        {"name": "test-success", "command": "echo 'success'"},
        {"name": "test-fail", "command": "exit 1"}
    ]
    (tmp_path / DEEP_DIR / "pipeline.json").write_text(json.dumps(config))
    
    return tmp_path, env


def test_pipeline_creation(pipeline_repo):
    repo, env = pipeline_repo
    runner = PipelineRunner(repo / DEEP_DIR)
    
    from deep.core.refs import resolve_head
    sha = resolve_head(repo / DEEP_DIR)
    
    run = runner.create_run(sha)
    assert run.commit_sha == sha
    assert len(run.jobs) == 2
    assert run.jobs[0].name == "test-success"


def test_pipeline_execution(pipeline_repo):
    repo, env = pipeline_repo
    runner = PipelineRunner(repo / DEEP_DIR)
    
    from deep.core.refs import resolve_head
    sha = resolve_head(repo / DEEP_DIR)
    
    run = runner.create_run(sha)
    runner.run_pipeline(run, env=env)
    
    assert run.status == "failed"  # Because one job fails
    assert run.jobs[0].status == "success"
    assert run.jobs[1].status == "failed"


def test_pipeline_cli_list(pipeline_repo):
    repo, env = pipeline_repo
    # Trigger a run via CLI
    subprocess.run(
        [sys.executable, "-m", "deep.main", "pipeline", "run"],
        cwd=repo, env=env, check=True
    )
    
    result = subprocess.run(
        [sys.executable, "-m", "deep.main", "pipeline", "list"],
        cwd=repo, env=env, capture_output=True, text=True, check=True
    )
    assert "run_" in result.stdout


def test_pipeline_cli_status(pipeline_repo):
    repo, env = pipeline_repo
    # Trigger a run
    subprocess.run(
        [sys.executable, "-m", "deep.main", "pipeline", "run"],
        cwd=repo, env=env, check=True
    )
    
    # Get run ID from list
    list_res = subprocess.run(
        [sys.executable, "-m", "deep.main", "pipeline", "list"],
        cwd=repo, env=env, capture_output=True, text=True, check=True
    )
    run_id = list_res.stdout.splitlines()[2].split()[0]
    
    # Check status
    status_res = subprocess.run(
        [sys.executable, "-m", "deep.main", "pipeline", "status", run_id],
        cwd=repo, env=env, capture_output=True, text=True, check=True
    )
    assert run_id in status_res.stdout
    assert "test-success" in status_res.stdout
    assert "test-fail" in status_res.stdout
