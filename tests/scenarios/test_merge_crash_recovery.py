import os
import pytest
from pathlib import Path
from deep.core.repository import init_repo,DEEP_DIR
from deep.storage.txlog import TransactionLog
from deep.core.refs import resolve_head
from deep.cli.main import main
from deep.core.errors import DeepCLIException

def test_merge_conflict_markers(tmp_path, monkeypatch):
    """Verify that merge conflicts write markers to the working directory."""
    repo_root = tmp_path / "repo"
    dg = init_repo(repo_root)
    monkeypatch.chdir(repo_root)
    
    # Base commit
    f = repo_root / "f.txt"
    f.write_text("base content\n")
    main(["add", "f.txt"])
    main(["commit", "-m", "base"])
    
    # Branch 'side'
    main(["branch", "side"])
    
    # Main change
    f.write_text("main content\n")
    main(["add", "f.txt"])
    main(["commit", "-m", "main change"])
    
    # Side change
    main(["checkout", "side"])
    f.write_text("side content\n")
    main(["add", "f.txt"])
    main(["commit", "-m", "side change"])
    
    # Merge 'main' into 'side'
    with pytest.raises(DeepCLIException):
        main(["merge", "main"])
    
    # Check for conflict markers
    content = f.read_text()
    assert "<<<<<<< OURS" in content
    assert "side content" in content
    assert "=======" in content
    assert "main content" in content
    assert ">>>>>>> THEIRS" in content

def test_merge_crash_recovery(tmp_path, monkeypatch):
    """Test WAL recovery for merge crashing before ref update."""
    repo_root = tmp_path / "repo"
    dg = init_repo(repo_root)
    monkeypatch.chdir(repo_root)
    
    # Base
    f = repo_root / "file.txt"
    f.write_text("base\n")
    main(["add", "file.txt"])
    main(["commit", "-m", "base"])
    base_sha = resolve_head(dg)
    
    # Side branch
    main(["branch", "side"])
    f.write_text("main\n")
    main(["add", "file.txt"])
    main(["commit", "-m", "main"])
    main_sha = resolve_head(dg)
    
    main(["checkout", "side"])
    f2 = repo_root / "other.txt"
    f2.write_text("other\n")
    main(["add", "other.txt"])
    main(["commit", "-m", "side"])
    side_sha = resolve_head(dg)
    
    # Simulate crash before ref update in 3-way merge
    monkeypatch.setenv("DEEP_CRASH_TEST", "MERGE_BEFORE_REF_UPDATE")
    
    with pytest.raises(BaseException, match="Deep: simulated crash before ref update"):
        main(["merge", "main"])
    
    # Verify state: HEAD still at side_sha, WAL active
    assert resolve_head(dg) == side_sha
    txlog = TransactionLog(dg)
    assert txlog.needs_recovery()
    
    # Recover
    txlog.recover()
    assert not txlog.needs_recovery()
    # It should have rolled forward and updated the branch to the new merge commit
    new_head = resolve_head(dg)
    assert new_head != side_sha
    assert (repo_root / "file.txt").read_text() == "main\n"
    assert (repo_root / "other.txt").read_text() == "other\n"
