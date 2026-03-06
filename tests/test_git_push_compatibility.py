"""
tests.test_git_push_compatibility
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Phase 7: Git Compatibility Integration Test.
Verify that DeepGit can create a repository with nested directories
and correctly push it to a standard Git server (using GitBridge logic).
"""

import subprocess
import os
from pathlib import Path
import pytest
from deep.cli.main import main
from deep.core.repository import DEEP_GIT_DIR
from deep.network.client import GitBridge

def test_git_push_compatibility(tmp_path: Path, monkeypatch):
    """
    1. Create a DeepGit repo with nested dirs.
    2. Commit.
    3. Initialize a bare Git repo as a remote.
    4. Use GitBridge to push.
    5. Verify Git accepts it.
    """
    # 1. Setup DeepGit Repo
    deep_repo = tmp_path / "deep_repo"
    deep_repo.mkdir()
    monkeypatch.chdir(deep_repo)
    main(["init"])
    
    # Create nested structure
    docs_dir = deep_repo / "docs"
    docs_dir.mkdir()
    (docs_dir / "index.md").write_text("# Index")
    (docs_dir / "setup.md").write_text("# Setup")
    
    src_dir = deep_repo / "src" / "utils"
    src_dir.mkdir(parents=True)
    (src_dir / "helper.py").write_text("def help(): pass")
    
    main(["add", "."])
    main(["commit", "-m", "Initial commit with nested trees"])
    
    # 2. Setup Bare Git Repo as Remote
    git_remote = tmp_path / "git_remote.git"
    git_remote.mkdir()
    subprocess.run(["git", "init", "--bare"], cwd=git_remote, check=True)
    
    # 3. Push via GitBridge
    # We'll use the GitBridge logic to push from deep_repo to git_remote
    dg_dir = deep_repo / DEEP_GIT_DIR
    bridge = GitBridge(dg_dir)
    
    # We need to set up the remote in DeepGit first
    main(["remote", "add", "origin", str(git_remote)])
    
    # Run push
    # This will trigger GitBridge.push which constructs a temp git repo and pushes
    try:
        main(["push", "origin", "main"])
    except SystemExit as e:
        if e.code != 0:
            # Capture failure
            raise
            
    # 4. Verify in the Git Remote
    # Try to ls-tree in the remote to see if 'docs' is a tree
    result = subprocess.run(
        ["git", "ls-tree", "main"], 
        cwd=git_remote, 
        capture_output=True, 
        text=True, 
        check=True
    )
    
    # Expected output:
    # 040000 tree <sha>	docs
    # 040000 tree <sha>	src
    print(f"\nls-tree output:\n{result.stdout}")
    assert "040000 tree" in result.stdout
    assert "docs" in result.stdout
    assert "src" in result.stdout
    
    # Verify 'docs' content
    result_docs = subprocess.run(
        ["git", "ls-tree", "main:docs"], 
        cwd=git_remote, 
        capture_output=True, 
        text=True, 
        check=True
    )
    print(f"\nls-tree HEAD:docs output:\n{result_docs.stdout}")
    assert "100644 blob" in result_docs.stdout
    assert "index.md" in result_docs.stdout
