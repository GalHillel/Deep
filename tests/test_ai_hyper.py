"""
tests.test_ai_hyper
~~~~~~~~~~~~~~~~~~~
Tests for Phase 51: Hyper Reality Mode - Predictive AI and Cross-Repo analysis.
"""

import pytest
import os
import shutil
from pathlib import Path
from deep.core.repository import init_repo
from deep.ai.assistant import DeepGitAI


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
def hyper_repo(tmp_path):
    repo_dir = tmp_path / "hyper_repo"
    repo_dir.mkdir()
    init_repo(repo_dir)
    return repo_dir


def test_predict_push_basic(hyper_repo):
    ai = DeepGitAI(hyper_repo)
    
    with chdir(hyper_repo):
        # Create initial commit on main
        app_py = hyper_repo / "app.py"
        app_py.write_text("print('hello')")
        
        from deep.commands.add_cmd import run as run_add
        from deep.commands.commit_cmd import run as run_commit
        
        class Args: pass
        
        add_args = Args()
        add_args.files = ["app.py"]
        run_add(add_args)
        
        commit_args = Args()
        commit_args.message = "initial"
        commit_args.sign = False
        run_commit(commit_args)
        
        # Predict push (should be clean as there's no divergence)
        result = ai.predict_conflicts_pre_push("main")
        assert "Prediction:" in result.text
        assert "looks clean" in result.text
        assert result.suggestion_type == "predict_push"


def test_cross_repo_detection(tmp_path):
    repo1 = tmp_path / "repo1"
    repo1.mkdir()
    init_repo(repo1)
    
    repo2 = tmp_path / "repo2"
    repo2.mkdir()
    init_repo(repo2)
    
    # Add shared dependency file
    (repo1 / "requirements.txt").write_text("pytest\n")
    (repo2 / "requirements.txt").write_text("pytest\n")
    
    ai = DeepGitAI(repo1)
    result = ai.cross_repo_analysis()
    
    assert "Detected" in result.text
    details = "".join(result.details)
    assert "repo2" in details
    assert "requirements.txt" in details


def test_predict_push_conflict_simulation(hyper_repo):
    ai = DeepGitAI(hyper_repo)
    
    with chdir(hyper_repo):
        # 1. Base commit
        f = hyper_repo / "conflict.txt"
        f.write_text("base\n")
        
        from deep.commands.add_cmd import run as run_add
        from deep.commands.commit_cmd import run as run_commit
        from deep.commands.branch_cmd import run as run_branch
        from deep.commands.checkout_cmd import run as run_checkout

        class Args: pass
        
        add_args = Args()
        add_args.files = ["conflict.txt"]
        run_add(add_args)
        
        commit_args = Args()
        commit_args.message = "base"
        commit_args.sign = False
        run_commit(commit_args)
        
        # 2. Branch 'other' modifies same line
        branch_args = Args()
        branch_args.name = "other"
        branch_args.start_point = "main"
        branch_args.delete = False
        branch_args.list = False
        run_branch(branch_args)
        
        checkout_args = Args()
        checkout_args.target = "other"
        run_checkout(checkout_args)
        
        f.write_text("other mod\n")
        run_add(add_args)
        commit_args.message = "other mod"
        run_commit(commit_args)
        
        # 3. Back to main, modify same line
        checkout_args.target = "main"
        run_checkout(checkout_args)
        
        f.write_text("main mod\n")
        run_add(add_args)
        commit_args.message = "main mod"
        run_commit(commit_args)
        
        # 4. Predict push (main -> other) should detect conflict
        result = ai.predict_conflicts_pre_push("other")
        assert "Potential conflicts" in result.text
        assert any("conflict.txt" in d for d in result.details)
