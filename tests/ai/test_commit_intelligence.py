import subprocess
import os
import pytest
from pathlib import Path
from deep.ai.assistant import DeepAI

def run_deep(*args, cwd=None, env=None, input_text=None):
    import sys
    cmd = [sys.executable, "-m", "deep.cli.main"] + list(args)
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, env=env, input=input_text)

def test_heuristic_docs(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    run_deep("init", cwd=repo)
    
    (repo / "README.md").write_text("# Documentation Update", encoding="utf-8")
    run_deep("add", "README.md", cwd=repo)
    
    ai = DeepAI(repo)
    sug = ai.suggest_commit_message()
    assert "docs" in sug.text
    assert "documentation" in sug.text

def test_heuristic_test(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    run_deep("init", cwd=repo)
    
    (repo / "tests").mkdir()
    (repo / "tests" / "test_logic.py").write_text("def test_one(): pass", encoding="utf-8")
    run_deep("add", "tests/test_logic.py", cwd=repo)
    
    ai = DeepAI(repo)
    sug = ai.suggest_commit_message()
    assert "test" in sug.text
    assert "coverage" in sug.text or "improve" in sug.text

def test_heuristic_feat_core(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    run_deep("init", cwd=repo)
    
    # Create a core-like directory structure
    (repo / "src" / "deep" / "core").mkdir(parents=True)
    file_path = repo / "src" / "deep" / "core" / "storage_engine.py"
    file_path.write_text("class StorageEngine:\n    def save(self): pass\n    def load(self): pass\n    def delete(self): pass\n", encoding="utf-8")
    
    run_deep("add", "src/deep/core/storage_engine.py", cwd=repo)
    
    ai = DeepAI(repo)
    sug = ai.suggest_commit_message()
    # It should detect 'core' or 'storage' as scope
    assert "feat" in sug.text
    assert "core" in sug.text or "storage" in sug.text
    assert "storage engine" in sug.text

def test_heuristic_fix_logic(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    run_deep("init", cwd=repo)
    
    (repo / "utils.py").write_text("def run(x):\n    return x + 1\n", encoding="utf-8")
    run_deep("add", "utils.py", cwd=repo)
    run_deep("commit", "-m", "initial", cwd=repo)
    
    # Small modification
    (repo / "utils.py").write_text("def run(x):\n    print(x)\n    return x + 1\n", encoding="utf-8")
    run_deep("add", "utils.py", cwd=repo)
    
    ai = DeepAI(repo)
    sug = ai.suggest_commit_message()
    assert "fix" in sug.text or "refactor" in sug.text

def test_heuristic_rename_detection(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    run_deep("init", cwd=repo)
    
    (repo / "old_helper.py").write_text("def help(): pass", encoding="utf-8")
    run_deep("add", "old_helper.py", cwd=repo)
    run_deep("commit", "-m", "initial", cwd=repo)
    
    # Rename: delete old, add new with similar content/name
    (repo / "old_helper.py").unlink()
    (repo / "new_helper.py").write_text("def help(): pass", encoding="utf-8")
    
    # In Deep Git, this is 'rm' + 'add'
    run_deep("rm", "old_helper.py", cwd=repo)
    run_deep("add", "new_helper.py", cwd=repo)
    
    ai = DeepAI(repo)
    sug = ai.suggest_commit_message()
    assert "refactor" in sug.text
    assert "rename" in sug.text or "move" in sug.text or "to" in sug.text

def test_cli_ai_commit_interactivity(tmp_path):
    """Verify that deep commit --ai works end-to-end."""
    repo = tmp_path / "repo"
    repo.mkdir()
    run_deep("init", cwd=repo)
    
    (repo / "core.py").write_text("x = 1\n", encoding="utf-8")
    run_deep("add", "core.py", cwd=repo)
    
    # Trigger AI commit and accept (y)
    res = run_deep("commit", "--ai", cwd=repo, input_text="y\n")
    assert res.returncode == 0
    assert "Deep: AI suggestion:" in res.stdout
    assert "initial" in res.stdout or "feat" in res.stdout
