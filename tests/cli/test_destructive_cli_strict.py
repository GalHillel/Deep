import os
import subprocess
import sys
import pytest
from pathlib import Path

def run_deep(*args, cwd=None):
    return subprocess.run(
        [sys.executable, "-m", "deep.cli.main", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(Path.cwd() / "src")}
    )

def test_cli_rm_safe(tmp_path):
    """
    Verify transactional file removal (rm updates index and WD).
    """
    run_deep("init", cwd=tmp_path)
    (tmp_path / "f1.txt").write_text("v1")
    run_deep("add", "f1.txt", cwd=tmp_path)
    run_deep("commit", "-m", "init", cwd=tmp_path)
    
    assert (tmp_path / "f1.txt").exists()
    
    res = run_deep("rm", "f1.txt", cwd=tmp_path)
    assert res.returncode == 0
    assert not (tmp_path / "f1.txt").exists()
    
    # Verify index
    from deep.storage.index import read_index
    idx = read_index(tmp_path / ".deep")
    assert "f1.txt" not in idx.entries

def test_cli_mv_safe(tmp_path):
    """
    Verify transactional file move (mv updates index and WD).
    """
    run_deep("init", cwd=tmp_path)
    (tmp_path / "src.txt").write_text("content")
    run_deep("add", "src.txt", cwd=tmp_path)
    run_deep("commit", "-m", "init", cwd=tmp_path)
    
    res = run_deep("mv", "src.txt", "dest.txt", cwd=tmp_path)
    assert res.returncode == 0
    assert not (tmp_path / "src.txt").exists()
    assert (tmp_path / "dest.txt").exists()
    
    # Verify index
    from deep.storage.index import read_index
    idx = read_index(tmp_path / ".deep")
    assert "src.txt" not in idx.entries
    assert "dest.txt" in idx.entries
    assert idx.entries["dest.txt"].content_hash is not None

def test_cli_reset_hard(tmp_path):
    """
    Verify atomic hard reset (HEAD, Index, and WD).
    """
    run_deep("init", cwd=tmp_path)
    
    # Commit 1
    (tmp_path / "f1.txt").write_text("v1")
    run_deep("add", "f1.txt", cwd=tmp_path)
    res1 = run_deep("commit", "-m", "c1", cwd=tmp_path)
    c1_sha = res1.stdout.strip().split()[-1] # Assuming it prints the SHA
    # Wait, commit prints something like "Created commit abc1234"
    # Actually let me just resolve HEAD
    from deep.core.refs import resolve_head
    c1_sha = resolve_head(tmp_path / ".deep")
    
    # Commit 2
    (tmp_path / "f1.txt").write_text("v2")
    (tmp_path / "f2.txt").write_text("v2")
    run_deep("add", "f1.txt", "f2.txt", cwd=tmp_path)
    run_deep("commit", "-m", "c2", cwd=tmp_path)
    
    assert (tmp_path / "f1.txt").read_text() == "v2"
    assert (tmp_path / "f2.txt").exists()
    
    # Hard reset to c1
    res = run_deep("reset", "--hard", c1_sha, cwd=tmp_path)
    assert res.returncode == 0
    
    assert (tmp_path / "f1.txt").read_text() == "v1"
    assert not (tmp_path / "f2.txt").exists()
    
    # Verify index
    from deep.storage.index import read_index
    idx = read_index(tmp_path / ".deep")
    assert "f1.txt" in idx.entries
    assert "f2.txt" not in idx.entries
    assert idx.entries["f1.txt"].content_hash is not None

def test_cli_mv_abort(tmp_path):
    """
    Verify rollback if move destination is blocked.
    """
    run_deep("init", cwd=tmp_path)
    (tmp_path / "file1.txt").write_text("v1")
    (tmp_path / "file2.txt").write_text("v2")
    run_deep("add", "file1.txt", "file2.txt", cwd=tmp_path)
    run_deep("commit", "-m", "init", cwd=tmp_path)
    
    # Try to move file1 to file2 (which exists)
    # The command should fail and roll back (though mv handles this check before mutation, 
    # but the transaction would catch any middle-failure).
    res = run_deep("mv", "file1.txt", "file2.txt", cwd=tmp_path)
    assert res.returncode != 0
    assert "exists" in res.stderr.lower()
    
    # Verify state is UNCHANGED
    assert (tmp_path / "file1.txt").exists()
    assert (tmp_path / "file1.txt").read_text() == "v1"
    assert (tmp_path / "file2.txt").exists()
    assert (tmp_path / "file2.txt").read_text() == "v2"
    
    from deep.storage.index import read_index
    idx = read_index(tmp_path / ".deep")
    assert "file1.txt" in idx.entries
    assert "file2.txt" in idx.entries
