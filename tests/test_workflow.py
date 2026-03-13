"""
tests.test_workflow
~~~~~~~~~~~~~~~~~~~
End-to-End Simulation of DeepGit usage in a standard workflow:
Init -> Edit -> Add -> Commit -> Branch -> Checkout -> Edit -> Add -> Commit -> Checkout Main -> Merge
"""

import sys
from pathlib import Path

import pytest
from deep.cli.main import build_parser
from deep.commands import init_cmd, add_cmd, commit_cmd, branch_cmd, checkout_cmd, merge_cmd, status_cmd

@pytest.fixture
def run_cli():
    """Helper to run CLI commands directly through their run() methods."""
    parser = build_parser()
    def _run(*args):
        # We parse the args to get the populated namespace
        parsed_args = parser.parse_args(args)
        cmd_name = parsed_args.command
        
        # Dispatch maps to run
        if cmd_name == "init": init_cmd.run(parsed_args)
        elif cmd_name == "add": add_cmd.run(parsed_args)
        elif cmd_name == "commit": commit_cmd.run(parsed_args)
        elif cmd_name == "branch": branch_cmd.run(parsed_args)
        elif cmd_name == "checkout": checkout_cmd.run(parsed_args)
        elif cmd_name == "merge": merge_cmd.run(parsed_args)
        elif cmd_name == "status": status_cmd.run(parsed_args)
        else:
            raise ValueError(f"Unknown command {cmd_name}")
            
    return _run

def test_full_local_workflow(tmp_path: Path, monkeypatch, run_cli):
    """Test a full standard developer workflow."""
    import os
    monkeypatch.chdir(tmp_path)
    
    # 1. INIT
    run_cli("init")
    assert (tmp_path / ".deep").exists()
    
    # 2. Add first file on main
    (tmp_path / "hello.txt").write_text("Hello, World!")
    run_cli("add", "hello.txt")
    run_cli("commit", "-m", "Initial commit")
    
    # 3. Create a branch and switch
    run_cli("branch", "feature-x")
    run_cli("checkout", "feature-x")
    
    # 4. Modify and commit on branch
    (tmp_path / "feature.txt").write_text("New feature")
    (tmp_path / "hello.txt").write_text("Hello, World! (updated)")
    run_cli("add", ".")
    run_cli("commit", "-m", "Add feature X")
    
    # 5. Switch back to main
    run_cli("checkout", "main")
    assert not (tmp_path / "feature.txt").exists()
    assert (tmp_path / "hello.txt").read_text() == "Hello, World!"
    
    # 6. Merge feature-x into main
    run_cli("merge", "feature-x")
    assert (tmp_path / "feature.txt").exists()
    assert (tmp_path / "hello.txt").read_text() == "Hello, World! (updated)"
    
    # 7. Check status is clean
    # Can't easily assert print output without capturing stdout, but we can verify it doesn't crash
    run_cli("status")
