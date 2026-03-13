"""
tests.test_super_status
~~~~~~~~~~~~~~~~~~~~~~
Tests for Phase 9 features:
1. Ahead/Behind metrics vs remote tracking branches
2. Porcelain status format
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from deep.core.repository import DEEP_DIR
from deep.cli.main import main
from deep.core.status import compute_status
from deep.core.refs import update_remote_ref, update_branch

def test_porcelain_status(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    os.chdir(repo)
    main(["init"])
    
    # Create changes
    (repo / "staged.txt").write_text("staged")
    main(["add", "staged.txt"])
    
    (repo / "modified.txt").write_text("modified")
    main(["add", "modified.txt"])
    main(["commit", "-m", "initial"])
    (repo / "modified.txt").write_text("modified v2")
    
    (repo / "untracked.txt").write_text("untracked")
    
    # Capture porcelain output
    from io import StringIO
    import sys
    
    old_stdout = sys.stdout
    sys.stdout = mystdout = StringIO()
    try:
        main(["status", "--porcelain"])
    finally:
        sys.stdout = old_stdout
        
    output = mystdout.getvalue()
    assert "M  modified.txt" in output or " M modified.txt" in output
    assert "?? untracked.txt" in output

def test_ahead_behind_metrics(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    os.chdir(repo)
    main(["init"])
    
    dg_dir = repo / DEEP_DIR
    
    # Setup: initial commit
    (repo / "f.txt").write_text("v1")
    main(["add", "f.txt"])
    main(["commit", "-m", "c1"])
    c1_sha = (dg_dir / "refs" / "heads" / "main").read_text().strip()
    
    # Setup remote tracking
    main(["config", "branch.main.remote", "origin"])
    main(["config", "branch.main.merge", "refs/heads/main"])
    
    # 1. Up to date
    from deep.core.refs import _remote_ref_path
    remote_path = _remote_ref_path(dg_dir, "origin", "main")
    remote_path.parent.mkdir(parents=True, exist_ok=True)
    remote_path.write_text(c1_sha + "\n")
    
    status = compute_status(repo)
    assert status.ahead_count == 0
    assert status.behind_count == 0
    
    # 2. Ahead
    (repo / "f.txt").write_text("v2")
    main(["add", "f.txt"])
    main(["commit", "-m", "c2"])
    
    status = compute_status(repo)
    assert status.ahead_count == 1
    assert status.behind_count == 0
    
    # 3. Behind (by resetting local)
    update_branch(dg_dir, "main", c1_sha)
    # Now local is c1, remote is c1, but let's make remote ahead of c1
    (repo / "f.txt").write_text("v3")
    main(["add", "f.txt"])
    main(["commit", "-m", "c3"])
    c3_sha = (dg_dir / "refs" / "heads" / "main").read_text().strip()
    # Now set remote to c3, and local back to c1
    remote_path.write_text(c3_sha + "\n")
    update_branch(dg_dir, "main", c1_sha)
    
    status = compute_status(repo)
    assert status.ahead_count == 0
    assert status.behind_count == 1
