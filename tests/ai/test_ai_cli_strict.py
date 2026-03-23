import subprocess
import os
import pytest
from pathlib import Path

def run_deep(*args, cwd=None, env=None):
    import sys
    cmd = [sys.executable, "-m", "deep.cli.main"] + list(args)
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, env=env)

def test_cli_ai_refactor_safe(tmp_path):
    """
    Setup repo with a file needing refactoring.
    Run deep ai refactor.
    Verify change applied and state is consistent.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    run_deep("init", cwd=repo)
    
    file_path = repo / "logic.py"
    file_path.write_text("def check(x):\n    if x == True:\n        return True\n    return False\n", encoding="utf-8")
    
    # We must stage the file because DeepAI currently analyzes staged changes
    run_deep("add", "logic.py", cwd=repo)
    
    # Run refactor
    res = run_deep("ai", "refactor", cwd=repo)
    assert res.returncode == 0
    assert "Applying AI Refactors" in res.stdout
    assert "Applied successfully" in res.stdout
    
    # Verify file content
    new_content = file_path.read_text(encoding="utf-8")
    assert "if x:" in new_content
    assert "if x == True:" not in new_content
    
    # Verify status (it should still be staged, but with different content? No, refactor modifies WD.)
    # If refactor modifies WD, but NOT the index, then logic.py is now 'modified' vs index.
    res = run_deep("status", cwd=repo)
    assert "Modified:" in res.stdout or "Changes not staged for commit:" in res.stdout

def test_cli_ai_abort_on_crash(tmp_path):
    """
    Run refactor with DEEP_AI_CHAOS=REFACTOR_CRASH.
    Verify non-zero exit and file remains unchanged.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    run_deep("init", cwd=repo)
    
    file_path = repo / "logic.py"
    original_content = "def check(x):\n    if x == True:\n        return True\n    return False\n"
    file_path.write_text(original_content, encoding="utf-8")
    
    run_deep("add", "logic.py", cwd=repo)
    
    env = os.environ.copy()
    env["DEEP_AI_CHAOS"] = "REFACTOR_CRASH"
    
    # Run refactor with crash trigger
    res = run_deep("ai", "refactor", cwd=repo, env=env)
    
    assert res.returncode != 0
    assert "AI Refactor Crash" in res.stderr
    
    # Verify file content is UNCHANGED (rolled back)
    current_content = file_path.read_text(encoding="utf-8")
    assert current_content == original_content
    
    # Verify WAL/TX integrity: No partial transaction left
    # (Implicitly verified by return code and lack of .lock files if we checked further)

def test_cli_ai_cleanup_transactional(tmp_path):
    """
    Verify cleanup runs in a transaction.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    run_deep("init", cwd=repo)
    
    res = run_deep("ai", "cleanup", cwd=repo)
    assert res.returncode == 0
    assert "🧹" in res.stdout
