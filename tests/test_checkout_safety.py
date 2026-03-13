import os
import shutil
import pytest
from pathlib import Path
from deep.core.repository import init_repo,DEEP_DIR
from deep.storage.txlog import TransactionLog
from deep.core.refs import resolve_head, update_branch
from deep.storage.index import read_index
from deep.cli.main import main

def test_checkout_safety_uncommitted_changes(tmp_path, monkeypatch):
    """Ensure checkout fails if uncommitted changes would be overwritten."""
    repo_root = tmp_path / "repo"
    dg = init_repo(repo_root)
    monkeypatch.chdir(repo_root)
    
    # 1. First commit
    f1 = repo_root / "test.txt"
    f1.write_text("v1")
    main(["add", "test.txt"])
    main(["commit", "-m", "v1"])
    v1_sha = resolve_head(dg)
    
    # 2. Second commit
    f1.write_text("v2")
    main(["add", "test.txt"])
    main(["commit", "-m", "v2"])
    v2_sha = resolve_head(dg)
    
    # Switch back to v1
    main(["checkout", v1_sha])
    
    # Modify file in WD (uncommitted modification)
    f1.write_text("modified")
    
    # Attempt to checkout v2 - should fail
    with pytest.raises(SystemExit) as cm:
        main(["checkout", v2_sha])
    assert cm.value.code == 1
    assert f1.read_text() == "modified" # Data preserved

def test_checkout_crash_recovery_after_head_update(tmp_path, monkeypatch):
    """Test recovery if crash happens after HEAD is updated but before WAL commit."""
    repo_root = tmp_path / "repo"
    dg = init_repo(repo_root)
    monkeypatch.chdir(repo_root)
    
    # Create two versions
    f = repo_root / "f.txt"
    f.write_text("v1")
    main(["add", "f.txt"])
    main(["commit", "-m", "v1"])
    v1_sha = resolve_head(dg)
    
    f.write_text("v2")
    main(["add", "f.txt"])
    main(["commit", "-m", "v2"])
    v2_sha = resolve_head(dg)
    
    # Go back to v1
    main(["checkout", v1_sha])
    
    # Simulate crash after HEAD update
    monkeypatch.setenv("DEEP_CRASH_TEST", "CHECKOUT_AFTER_HEAD_UPDATE")
    
    with pytest.raises(BaseException, match="DeepBridge: simulated crash after HEAD update"):
        main(["checkout", v2_sha])
    
    # Verify state: HEAD is v2, but WAL transaction is still active (uncommitted)
    assert resolve_head(dg) == v2_sha
    txlog = TransactionLog(dg)
    assert txlog.needs_recovery()
    
    # Recover
    txlog.recover()
    assert not txlog.needs_recovery()
    assert resolve_head(dg) == v2_sha
    assert f.read_text() == "v2"

def test_checkout_crash_recovery_before_wd_update(tmp_path, monkeypatch):
    """Test recovery if crash happens before WD update."""
    repo_root = tmp_path / "repo"
    dg = init_repo(repo_root)
    monkeypatch.chdir(repo_root)
    
    f = repo_root / "f.txt"
    f.write_text("v1")
    main(["add", "f.txt"])
    main(["commit", "-m", "v1"])
    v1_sha = resolve_head(dg)
    
    f.write_text("v2")
    main(["add", "f.txt"])
    main(["commit", "-m", "v2"])
    v2_sha = resolve_head(dg)
    
    main(["checkout", v1_sha])
    
    monkeypatch.setenv("DEEP_CRASH_TEST", "CHECKOUT_BEFORE_WD_UPDATE")
    
    with pytest.raises(BaseException, match="DeepBridge: simulated crash before working directory update"):
        main(["checkout", v2_sha])
    
    # Verify state: HEAD is still v1 (or ref-update hasn't happened yet)
    # Actually in checkout_cmd.py, HEAD update happens AFTER WD update.
    assert resolve_head(dg) == v1_sha
    txlog = TransactionLog(dg)
    assert txlog.needs_recovery()
    
    # Recover
    txlog.recover()
    assert not txlog.needs_recovery()
    assert resolve_head(dg) == v2_sha
    assert f.read_text() == "v2"

def test_checkout_force_overwrites(tmp_path, monkeypatch):
    """Ensure checkout --force overwrites uncommitted changes."""
    repo_root = tmp_path / "repo"
    dg = init_repo(repo_root)
    monkeypatch.chdir(repo_root)
    
    f1 = repo_root / "test.txt"
    f1.write_text("v1")
    main(["add", "test.txt"])
    main(["commit", "-m", "v1"])
    v1_sha = resolve_head(dg)
    
    f1.write_text("v2")
    main(["add", "test.txt"])
    main(["commit", "-m", "v2"])
    v2_sha = resolve_head(dg)
    
    main(["checkout", v1_sha])
    f1.write_text("uncommitted change")
    
    # This should succeed with --force
    main(["checkout", "--force", v2_sha])
    assert f1.read_text() == "v2"
    assert resolve_head(dg) == v2_sha
