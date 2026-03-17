"""
tests.test_ai_refactor
~~~~~~~~~~~~~~~~~~~~~~
Tests for Phase 52: AI Auto-Refactor Engine.
"""

import pytest
import os
from pathlib import Path
from deep.core.repository import init_repo
from deep.ai.assistant import DeepAI

import contextlib

@contextlib.contextmanager
def chdir(path):
    old_cwd = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old_cwd)


@pytest.fixture
def refactor_repo(tmp_path):
    repo_dir = tmp_path / "refactor_repo"
    repo_dir.mkdir()
    init_repo(repo_dir)
    return repo_dir


def test_ai_refactor_suggestions(refactor_repo):
    ai = DeepAI(refactor_repo)
    
    with chdir(refactor_repo):
        # Create a file with "unclean" code
        code_py = refactor_repo / "logic.py"
        code_py.write_text("if x == True:\n    print('dirty code')\n")
        
        from deep.commands.add_cmd import run as run_add
        class Args: pass
        add_args = Args()
        add_args.files = ["logic.py"]
        run_add(add_args)
        
        # Get refactor suggestions
        results = ai.suggest_refactors()
        assert len(results) >= 2 # One for boolean, one for print()
        
        # Check details
        found_bool = False
        found_print = False
        for r in results:
            if "boolean" in r.details[0].lower():
                found_bool = True
            if "print" in r.details[0].lower():
                found_print = True
                
        assert found_bool
        assert found_print


def test_ai_refactor_no_issues(refactor_repo):
    ai = DeepAI(refactor_repo)
    
    with chdir(refactor_repo):
        clean_py = refactor_repo / "clean.py"
        clean_py.write_text("def main():\n    return 42\n")
        
        from deep.commands.add_cmd import run as run_add
        class Args: pass
        add_args = Args()
        add_args.files = ["clean.py"]
        run_add(add_args)
        
        results = ai.suggest_refactors()
        assert len(results) == 0
