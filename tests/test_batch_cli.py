"""Tests for batch CLI and scripting mode (Phase 39)."""
from pathlib import Path
import subprocess, sys, os
import pytest

from deep_git.core.repository import DEEP_GIT_DIR


@pytest.fixture
def batch_repo(tmp_path):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path.cwd())
    subprocess.run([sys.executable, "-m", "deep_git.main", "init"], cwd=tmp_path, env=env, check=True)
    return tmp_path, env


def test_batch_add_and_commit(batch_repo):
    repo, env = batch_repo
    (repo / "x.txt").write_text("x")
    (repo / "y.txt").write_text("y")
    script = repo / "ops.dgit"
    script.write_text("add x.txt y.txt\ncommit -m \"batch commit\"\n")
    result = subprocess.run(
        [sys.executable, "-m", "deep_git.main", "batch", str(script)],
        cwd=repo, env=env, capture_output=True, text=True,
    )
    assert result.returncode == 0
    assert "Batch complete" in result.stdout


def test_batch_with_comments(batch_repo):
    repo, env = batch_repo
    (repo / "z.txt").write_text("z")
    script = repo / "ops.dgit"
    script.write_text("# This is a comment\nadd z.txt\n# Another comment\ncommit -m \"add z\"\n")
    result = subprocess.run(
        [sys.executable, "-m", "deep_git.main", "batch", str(script)],
        cwd=repo, env=env, capture_output=True, text=True,
    )
    assert result.returncode == 0


def test_batch_nonexistent_script(batch_repo):
    repo, env = batch_repo
    result = subprocess.run(
        [sys.executable, "-m", "deep_git.main", "batch", "nonexistent.dgit"],
        cwd=repo, env=env, capture_output=True, text=True,
    )
    assert result.returncode != 0
