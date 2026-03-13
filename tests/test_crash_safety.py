"""
tests.test_crash_safety
~~~~~~~~~~~~~~~~~~~~~~~~
Verify that DeepGit can recover from crashes using the Transaction Log (WAL).
"""

import json
import time
from pathlib import Path

import pytest
from deep.storage.txlog import TransactionLog, TxRecord
from deep.core.repository import DEEP_DIR
from deep.core.refs import update_branch, get_branch
from deep.cli.main import main

def test_recovery_on_interrupted_commit(tmp_path: Path, monkeypatch, capsys):
    """
    Simulate a crash during commit:
    1. BEGIN record is written.
    2. Commit objects are NOT written (or partially).
    3. No COMMIT record.
    4. Verify recovery rolls back the branch.
    """
    monkeypatch.chdir(tmp_path)
    
    # Setup repo
    from deep.commands import init_cmd, add_cmd, commit_cmd
    from argparse import Namespace
    init_cmd.run(Namespace(path=None))
    dg_dir = tmp_path / DEEP_DIR
    
    # Create first commit normally
    (tmp_path / "a.txt").write_text("a")
    add_cmd.run(Namespace(files=["a.txt"], all=False))
    commit_cmd.run(Namespace(message="Initial", sign=False))
    
    initial_sha = get_branch(dg_dir, "main")
    assert initial_sha is not None
    
    # Now simulate a CRASH during a second commit
    txlog = TransactionLog(dg_dir)
    # We manually write a BEGIN record for a commit that was going to change main to 'deadbeef'
    tx_id = txlog.begin(
        operation="commit",
        branch_ref="main",
        previous_commit_sha=initial_sha,
        target_object_id="d" * 40
    )
    
    # We do NOT write the objects or the COMMIT record.
    # Run status to trigger recovery
    try:
        main(["status"])
    except SystemExit:
        pass
        
    # Check stderr for "Running crash recovery..."
    captured = capsys.readouterr()
    assert "Running crash recovery..." in captured.err
    
    # Verify that the branch is still pointing to initial_sha (rolled back from the 'deadbeef' attempt)
    assert get_branch(dg_dir, "main") == initial_sha
    
    # Verify transaction is now rolled back in the log
    records = txlog.read_all()
    assert records[-1].status == "ROLLBACK"
    assert records[-1].tx_id == tx_id

def test_recovery_roll_forward(tmp_path: Path, monkeypatch, capsys):
    """
    Simulate a crash AFTER objects are written but BEFORE txlog COMMIT:
    1. BEGIN record is written.
    2. Commit objects ARE written.
    3. Branch pointer might or might not be updated.
    4. No txlog COMMIT record.
    5. Verify recovery rolls forward (ensures branch is updated).
    """
    monkeypatch.chdir(tmp_path)
    
    # Setup repo
    from deep.commands import init_cmd, add_cmd, commit_cmd
    from argparse import Namespace
    init_cmd.run(Namespace(path=None))
    dg_dir = tmp_path / DEEP_DIR
    
    # Create first commit
    (tmp_path / "a.txt").write_text("a")
    add_cmd.run(Namespace(files=["a.txt"], all=False))
    commit_cmd.run(Namespace(message="Initial", sign=False))
    initial_sha = get_branch(dg_dir, "main")
    
    # Manually create a second commit object
    from deep.storage.objects import Commit, Tree
    tree = Tree(entries=[])
    tree_sha = tree.write(dg_dir / "objects")
    new_commit = Commit(tree_sha=tree_sha, parent_shas=[initial_sha], message="Second", author="test", committer="test", timestamp=int(time.time()))
    new_sha = new_commit.write(dg_dir / "objects")
    
    # Simulate partial commit: BEGIN written, Objects written, but crashed before COMMIT record
    txlog = TransactionLog(dg_dir)
    tx_id = txlog.begin(
        operation="commit",
        branch_ref="main",
        previous_commit_sha=initial_sha,
        target_object_id=new_sha
    )
    
    # Ensure branch still points to initial_sha
    update_branch(dg_dir, "main", initial_sha)
    
    # Run status to trigger recovery
    try:
        main(["status"])
    except SystemExit:
        pass
        
    # Verify recovery rolled FORWARD because objects exist
    assert get_branch(dg_dir, "main") == new_sha
    
    # Verify log entry is COMMIT
    records = txlog.read_all()
    assert records[-1].status == "COMMIT"
    assert records[-1].tx_id == tx_id
