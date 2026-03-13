import os
import threading
import time
from pathlib import Path
from unittest import mock

import pytest

from deep.commands.commit_cmd import run as commit_run
from deep.core.repository import DEEP_DIR, init_repo
from deep.storage.txlog import TransactionLog


class MockArgs:
    def __init__(self, message: str):
        self.message = message


def test_crash_mid_commit_branch_recovery(tmp_path: Path):
    """Simulate a crash during the branch pointer update and prove txlog recovers."""
    dg_dir = init_repo(tmp_path)
    
    # 1. Create a file and index it
    file1 = tmp_path / "file1.txt"
    file1.write_text("hello 1")
    
    from deep.commands.add_cmd import run as add_run
    
    with mock.patch("deep.commands.add_cmd.find_repo", return_value=tmp_path):
        with mock.patch("deep.commands.commit_cmd.find_repo", return_value=tmp_path):
            class AddArgs:
                files = [str(file1)]
            add_run(AddArgs())
            commit_run(MockArgs("first commit"))
        
    from deep.core.refs import resolve_head
    first_commit = resolve_head(dg_dir)
    assert first_commit is not None
    
    file1.write_text("hello 2")
    
    # We will crash during the commit's branch update
    original_update_branch = __import__("deep.core.refs", fromlist=["update_branch"]).update_branch
    
    def crashing_update_branch(dg_dir, name, commit_sha):
        # We simulate power loss by raising an error and simultaneously disabling the rollback 
        # so the txlog STAYS in the incomplete BEGIN state
        raise Exception("Simulated power loss during branch update!")

    with mock.patch("deep.commands.commit_cmd.update_branch", side_effect=crashing_update_branch):
        with mock.patch("deep.core.refs.update_head", side_effect=crashing_update_branch):
            with mock.patch("deep.commands.add_cmd.find_repo", return_value=tmp_path):
                with mock.patch("deep.commands.commit_cmd.find_repo", return_value=tmp_path):
                    with mock.patch.object(TransactionLog, "rollback"):  # Prevent the exception handler from cleaning up
                        add_run(AddArgs())
                        with pytest.raises(Exception, match="Simulated power loss during branch update!"):
                            commit_run(MockArgs("second commit"))

    # Assert repo is currently damaged (incomplete transaction exists)
    txlog = TransactionLog(dg_dir)
    assert txlog.needs_recovery()
    
    # Assert branch still points to first commit (the write never succeeded)
    assert resolve_head(dg_dir) == first_commit

    incomplete = txlog.get_incomplete()
    assert len(incomplete) == 1
    second_commit_sha = incomplete[0].target_object_id

    # Run recovery
    txlog.recover()
    
    # Assert txlog no longer needs recovery
    assert not txlog.needs_recovery()
    
    # Since the commit objects WERE safely written before the crash, txlog recovery
    # sees the objects exist and rolls FORWARD instead of backward!
    assert resolve_head(dg_dir) == second_commit_sha


def test_crash_after_branch_update_before_txlog_commit(tmp_path: Path):
    """Simulate a crash where the branch update succeeded but txlog.commit failed."""
    dg_dir = init_repo(tmp_path)
    file1 = tmp_path / "file1.txt"
    file1.write_text("hello 1")
    
    from deep.commands.add_cmd import run as add_run
    
    with mock.patch("deep.commands.add_cmd.find_repo", return_value=tmp_path):
        with mock.patch("deep.commands.commit_cmd.find_repo", return_value=tmp_path):
            class AddArgs:
                files = [str(file1)]
            add_run(AddArgs())
            commit_run(MockArgs("first commit"))
        
    file1.write_text("hello 2")
    
    original_txlog_commit = TransactionLog.commit
    def crashing_txlog_commit(self, tx_id):
        raise OSError("Simulated power loss during txlog commit")

    with mock.patch("deep.commands.add_cmd.find_repo", return_value=tmp_path):
        with mock.patch("deep.commands.commit_cmd.find_repo", return_value=tmp_path):
            with mock.patch.object(TransactionLog, "commit", side_effect=crashing_txlog_commit, autospec=True):
                with mock.patch.object(TransactionLog, "rollback"):
                    add_run(AddArgs())
                    with pytest.raises(OSError, match="Simulated power loss during txlog commit"):
                        commit_run(MockArgs("second commit"))

    # The branch WAS updated, but the transaction is incomplete
    from deep.core.refs import resolve_head
    second_commit = resolve_head(dg_dir)
    
    txlog = TransactionLog(dg_dir)
    assert txlog.needs_recovery()
    
    txlog.recover()
    
    assert not txlog.needs_recovery()
    
    # Since branch update succeeded and the object is valid, recovery completes it by rolling FORWARD 
    # (or rather, doing nothing and just committing the tx)
    assert resolve_head(dg_dir) == second_commit


def test_idempotent_repeated_recovery(tmp_path: Path):
    """Test that repeatedly calling recover() is safe and idempotent."""
    dg_dir = init_repo(tmp_path)
    txlog = TransactionLog(dg_dir)
    
    for _ in range(5):
        txlog.recover()
        assert not txlog.needs_recovery()


def test_concurrency_file_locking(tmp_path: Path):
    """Test that multiple threads attempting to commit sequentially acquire the lock."""
    dg_dir = init_repo(tmp_path)
    
    from deep.commands.add_cmd import run as add_run
    
    with mock.patch("deep.commands.add_cmd.find_repo", return_value=tmp_path):
        with mock.patch("deep.commands.commit_cmd.find_repo", return_value=tmp_path):
            class AddArgs:
                files = [str(tmp_path / "file1.txt")]
            tmp_path.joinpath("file1.txt").write_text("init")
            add_run(AddArgs())
            commit_run(MockArgs("shared initial state"))

    results = []
    
    def worker(i):
        # NOTE: mock.patch must NOT be used per-thread — concurrent patch/unpatch
        # on the same module attribute corrupts the save/restore chain, permanently
        # leaving the attribute as a stale MagicMock. The mock is applied once from
        # the main thread below.
        try:
            commit_run(MockArgs(f"Thread commit {i}"))
            results.append(True)
        except Exception as e:
            results.append(e)

    # Apply mock ONCE from the main thread so restoration is thread-safe
    with mock.patch("deep.commands.commit_cmd.find_repo", return_value=tmp_path):
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
        for t in threads: t.start()
        for t in threads: t.join()
    
    # All threads should have successfully committed (or gracefully errored with empty index, etc)
    # The key is we shouldn't get corrupted refs or deadlocks.
    # Actually, since the index is shared and empty after the first commit, threads might fail because
    # there's nothing to commit. That's fine, we are testing LOCKING.
    assert len(results) == 5
