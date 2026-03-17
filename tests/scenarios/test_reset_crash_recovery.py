import os
import pytest
from pathlib import Path
from deep.core.repository import init_repo,DEEP_DIR
from deep.storage.txlog import TransactionLog
from deep.core.refs import resolve_head
from deep.cli.main import main

def test_reset_crash_recovery_hard(tmp_path, monkeypatch):
    """Test WAL recovery for reset --hard crashing before ref update."""
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
    
    # Simulate crash before ref update
    monkeypatch.setenv("DEEP_CRASH_TEST", "RESET_BEFORE_REF_UPDATE")
    
    with pytest.raises(BaseException, match="Deep: simulated crash before ref update"):
        main(["reset", "--hard", v1_sha])
    
    # State: HEAD is still v2, but index and WD might have been partially updated (hard reset)
    # Actually, reset_cmd updates WD/Index then HEAD.
    assert resolve_head(dg) == v2_sha
    txlog = TransactionLog(dg)
    assert txlog.needs_recovery()
    
    # Recover
    txlog.recover()
    assert resolve_head(dg) == v1_sha
    assert f.read_text() == "v1"

def test_reset_crash_recovery_soft(tmp_path, monkeypatch):
    """Test WAL recovery for reset --soft crashing before ref update."""
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
    
    monkeypatch.setenv("DEEP_CRASH_TEST", "RESET_BEFORE_REF_UPDATE")
    
    with pytest.raises(BaseException, match="Deep: simulated crash before ref update"):
        main(["reset", "--soft", v1_sha])
    
    assert resolve_head(dg) == v2_sha
    txlog = TransactionLog(dg)
    assert txlog.needs_recovery()
    
    txlog.recover()
    assert resolve_head(dg) == v1_sha
    # soft reset should NOT touch WD
    assert f.read_text() == "v2"

def test_reset_crash_recovery_mixed(tmp_path, monkeypatch):
    """Test WAL recovery for reset --mixed crashing before ref update."""
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
    
    monkeypatch.setenv("DEEP_CRASH_TEST", "RESET_BEFORE_REF_UPDATE")
    
    with pytest.raises(BaseException, match="Deep: simulated crash before ref update"):
        main(["reset", v1_sha]) # Mixed is default
    
    assert resolve_head(dg) == v2_sha
    txlog = TransactionLog(dg)
    assert txlog.needs_recovery()
    
    txlog.recover()
    assert resolve_head(dg) == v1_sha
    # mixed reset should NOT touch WD
    assert f.read_text() == "v2"
    # but it should update the index (checked by compute_status)
    from deep.core.status import compute_status
    status = compute_status(repo_root)
    assert "f.txt" in status.modified
