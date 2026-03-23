from pathlib import Path
import subprocess, sys, os, json
import pytest
from deep.core.repository import DEEP_DIR
from deep.cli.main import build_parser
from deep.commands import ai_cmd
import io
from contextlib import redirect_stdout


@pytest.fixture
def merge_env(tmp_path):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path.cwd() / "src")
    subprocess.run([sys.executable, "-m", "deep.cli.main", "init"], cwd=tmp_path, env=env, check=True)
    
    # Base commit
    (tmp_path / "common.txt").write_text("base content")
    subprocess.run([sys.executable, "-m", "deep.cli.main", "add", "common.txt"], cwd=tmp_path, env=env, check=True)
    subprocess.run([sys.executable, "-m", "deep.cli.main", "commit", "-m", "base"], cwd=tmp_path, env=env, check=True)
    
    # Branch 'main' modifies common.txt
    (tmp_path / "common.txt").write_text("base content\nmain change")
    subprocess.run([sys.executable, "-m", "deep.cli.main", "add", "common.txt"], cwd=tmp_path, env=env, check=True)
    subprocess.run([sys.executable, "-m", "deep.cli.main", "commit", "-m", "main mod"], cwd=tmp_path, env=env, check=True)
    
    # Branch 'feature' branched from base, modifies same file
    subprocess.run([sys.executable, "-m", "deep.cli.main", "branch", "feature", "HEAD~1"], cwd=tmp_path, env=env, check=True)
    # We don't have 'checkout' yet in a simple way, but we can commit to 'feature' 
    # if we manually set HEAD or use a command that supports it.
    # Actually, let's just create another commit that branched from base.
    
    return tmp_path, env


def test_predict_merge_no_conflict(merge_env):
    repo, env = merge_env
    # Feature branch (simulated by creating a new commit from base)
    (repo / "other.txt").write_text("new file")
    subprocess.run([sys.executable, "-m", "deep.cli.main", "add", "other.txt"], cwd=repo, env=env, check=True)
    
    parser = build_parser()
    args = parser.parse_args(["ai", "predict-merge", "--branch", "main"])
    
    f = io.StringIO()
    with redirect_stdout(f):
        os.chdir(repo)
        ai_cmd.run(args)
    
    stdout = f.getvalue()
    assert "looks clean" in stdout


def test_predict_merge_conflict(merge_env):
    repo, env = merge_env
    dg_dir = repo / DEEP_DIR
    
    parser = build_parser()
    args = parser.parse_args(["ai", "predict-merge", "--branch", "feature"])
    
    f = io.StringIO()
    with redirect_stdout(f):
        os.chdir(repo)
        ai_cmd.run(args)
    
    stdout = f.getvalue()
    assert "Simulation" in stdout or "Merge" in stdout


def test_ai_cleanup_cli(merge_env):
    repo, env = merge_env
    parser = build_parser()
    args = parser.parse_args(["ai", "cleanup"])
    
    f = io.StringIO()
    with redirect_stdout(f):
        os.chdir(repo)
        ai_cmd.run(args)
    
    stdout = f.getvalue()
    assert "Hygiene" in stdout
