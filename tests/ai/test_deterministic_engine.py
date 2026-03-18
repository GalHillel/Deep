import os
import subprocess
import sys
from pathlib import Path
import pytest
from deep.ai.assistant import DeepAI
from deep.storage.index import read_index

@pytest.fixture
def ai_repo(tmp_path):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path.cwd() / "src")
    subprocess.run([sys.executable, "-m", "deep.cli.main", "init"], cwd=tmp_path, env=env, check=True)
    return tmp_path

def test_infra_dependency_update(ai_repo):
    (ai_repo / "requirements.txt").write_text("pytest==7.0.0\n")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path.cwd() / "src")
    subprocess.run([sys.executable, "-m", "deep.cli.main", "add", "requirements.txt"], cwd=ai_repo, env=env, check=True)
    
    ai = DeepAI(ai_repo)
    result = ai.suggest_commit_message()
    assert result.text == "chore(deps): update dependencies"
    assert result.confidence == 0.95

def test_logic_change_message(ai_repo):
    (ai_repo / "core_logic.py").write_text("def process(x):\n    return x + 1\n")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path.cwd() / "src")
    subprocess.run([sys.executable, "-m", "deep.cli.main", "add", "core_logic.py"], cwd=ai_repo, env=env, check=True)
    subprocess.run([sys.executable, "-m", "deep.cli.main", "commit", "-m", "initial"], cwd=ai_repo, env=env, check=True)
    
    (ai_repo / "core_logic.py").write_text("def process(x):\n    if x > 10:\n        return x * 2\n    return x + 1\n")
    subprocess.run([sys.executable, "-m", "deep.cli.main", "add", "core_logic.py"], cwd=ai_repo, env=env, check=True)
    
    ai = DeepAI(ai_repo)
    result = ai.suggest_commit_message()
    # The new engine should detect 'process' in context lines
    assert "fix(core): update process logic" in result.text
    assert result.confidence == 0.80

def test_error_handling_message(ai_repo):
    (ai_repo / "api_helper.py").write_text("def get_data():\n    return {}\n")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path.cwd() / "src")
    subprocess.run([sys.executable, "-m", "deep.cli.main", "add", "api_helper.py"], cwd=ai_repo, env=env, check=True)
    subprocess.run([sys.executable, "-m", "deep.cli.main", "commit", "-m", "initial"], cwd=ai_repo, env=env, check=True)
    
    (ai_helper_path := ai_repo / "api_helper.py").write_text("def get_data():\n    try:\n        return {}\n    except Exception:\n        raise ValueError('failed')\n")
    subprocess.run([sys.executable, "-m", "deep.cli.main", "add", "api_helper.py"], cwd=ai_repo, env=env, check=True)
    
    ai = DeepAI(ai_repo)
    result = ai.suggest_commit_message()
    assert "fix(api): improve error handling" in result.text
    assert result.confidence == 0.80

def test_large_refactor_confidence(ai_repo):
    # Use 150 methods to exceed the 100-line 'large' threshold
    content = "class BigSystem:\n" + "\n".join([f"    def method_{i}(self): pass" for i in range(150)])
    (ai_repo / "core_system.py").write_text(content)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path.cwd() / "src")
    subprocess.run([sys.executable, "-m", "deep.cli.main", "add", "core_system.py"], cwd=ai_repo, env=env, check=True)
    
    ai = DeepAI(ai_repo)
    result = ai.suggest_commit_message()
    assert "feat(core): add new functionality" in result.text
    assert result.confidence > 0.85
    assert "large" in result.details[0]
