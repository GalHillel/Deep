from pathlib import Path
import subprocess, sys, os, json
import pytest
from deep.core.repository import DEEP_DIR
from deep.cli.main import build_parser
from deep.commands import ai_cmd
import io
from contextlib import redirect_stdout


@pytest.fixture
def ai_review_repo(tmp_path):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path.cwd() / "src")
    subprocess.run([sys.executable, "-m", "deep.cli.main", "init"], cwd=tmp_path, env=env, check=True)
    
    # Create an initial commit
    (tmp_path / "main.py").write_text("print('hello')")
    subprocess.run([sys.executable, "-m", "deep.cli.main", "add", "main.py"], cwd=tmp_path, env=env, check=True)
    subprocess.run([sys.executable, "-m", "deep.cli.main", "commit", "-m", "initial"], cwd=tmp_path, env=env, check=True)
    
    return tmp_path, env


def test_ai_review_findings(ai_review_repo):
    repo, env = ai_review_repo
    # Add a TODO and a secret
    (repo / "main.py").write_text("print('hello')\n# TODO: fix this\nAPI_KEY = 'secret'")
    subprocess.run([sys.executable, "-m", "deep.cli.main", "add", "main.py"], cwd=repo, env=env, check=True)
    
    parser = build_parser()
    args = parser.parse_args(["ai", "review"])
    
    f = io.StringIO()
    with redirect_stdout(f):
        os.chdir(repo)
        ai_cmd.run(args)
    
    stdout = f.getvalue()
    assert "TODO found" in stdout
    assert "Sensitive keyword" in stdout


def test_ai_review_clean(ai_review_repo):
    repo, env = ai_review_repo
    # No changes
    parser = build_parser()
    args = parser.parse_args(["ai", "review"])
    
    f = io.StringIO()
    with redirect_stdout(f):
        os.chdir(repo)
        ai_cmd.run(args)
    
    stdout = f.getvalue()
    assert "No critical issues found" in stdout


def test_ai_predict_merge_cli(ai_review_repo):
    repo, env = ai_review_repo
    parser = build_parser()
    args = parser.parse_args(["ai", "predict-merge"])
    
    f = io.StringIO()
    with redirect_stdout(f):
        os.chdir(repo)
        ai_cmd.run(args)
    
    stdout = f.getvalue()
    assert "Prediction:" in stdout


def test_ai_review_api(ai_review_repo):
    from deep.ai.assistant import DeepAI
    repo, env = ai_review_repo
    # Add a TODO
    (repo / "main.py").write_text("print('hello')\n# TODO: wait")
    subprocess.run([sys.executable, "-m", "deep.cli.main", "add", "main.py"], cwd=repo, env=env, check=True)

    ai = DeepAI(repo)
    res = ai.review_changes()
    assert any("TODO" in d for d in res.details)
