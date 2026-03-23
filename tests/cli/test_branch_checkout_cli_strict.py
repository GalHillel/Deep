import os
import subprocess
import sys
import time
import multiprocessing
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

def test_cli_branch_create(tmp_path):
    """
    Verify basic branch creation via CLI.
    """
    run_deep("init", cwd=tmp_path)
    (tmp_path / "f1.txt").write_text("v1")
    run_deep("add", "f1.txt", cwd=tmp_path)
    run_deep("commit", "-m", "initial", cwd=tmp_path)
    
    # Create branch
    res = run_deep("branch", "feat-1", cwd=tmp_path)
    assert res.returncode == 0
    
    # Verify ref exists and matches HEAD
    dg_dir = tmp_path / ".deep"
    head_sha = (dg_dir / "refs" / "heads" / "main").read_text().strip()
    feat_sha = (dg_dir / "refs" / "heads" / "feat-1").read_text().strip()
    assert feat_sha == head_sha

def _branch_worker(tmp_path, branch_name):
    # Small random sleep to increase collision chance
    import random
    time.sleep(random.random() * 0.1)
    return run_deep("branch", branch_name, cwd=tmp_path).returncode

def test_cli_branch_concurrent(tmp_path):
    """
    Verify concurrent branch creation is handled safely by RepoLock.
    """
    run_deep("init", cwd=tmp_path)
    (tmp_path / "f1.txt").write_text("v1")
    run_deep("add", "f1.txt", cwd=tmp_path)
    run_deep("commit", "-m", "initial", cwd=tmp_path)
    
    branch_names = [f"branch-{i}" for i in range(5)]
    
    with multiprocessing.Pool(5) as pool:
        results = pool.starmap(_branch_worker, [(tmp_path, name) for name in branch_names])
    
    assert all(r == 0 for r in results), f"Some concurrent branch creations failed: {results}"
    
    # Verify all branches exist
    dg_dir = tmp_path / ".deep"
    for name in branch_names:
        assert (dg_dir / "refs" / "heads" / name).exists()

def test_cli_checkout_safe(tmp_path):
    """
    Verify safe switching between branches and WD updates.
    """
    run_deep("init", cwd=tmp_path)
    
    # Commit 1 on main
    (tmp_path / "f1.txt").write_text("main-v1")
    run_deep("add", "f1.txt", cwd=tmp_path)
    run_deep("commit", "-m", "main 1", cwd=tmp_path)
    
    # Create and checkout dev
    run_deep("branch", "dev", cwd=tmp_path)
    run_deep("checkout", "dev", cwd=tmp_path)
    
    # Commit 2 on dev
    (tmp_path / "f2.txt").write_text("dev-v1")
    run_deep("add", "f2.txt", cwd=tmp_path)
    run_deep("commit", "-m", "dev 1", cwd=tmp_path)
    
    assert (tmp_path / "f1.txt").exists()
    assert (tmp_path / "f2.txt").exists()
    
    # Checkout main
    res = run_deep("checkout", "main", cwd=tmp_path)
    assert res.returncode == 0
    
    # f2.txt should be gone (it wasn't in main), f1.txt stays
    assert (tmp_path / "f1.txt").exists()
    assert not (tmp_path / "f2.txt").exists()
    assert (tmp_path / "f1.txt").read_text() == "main-v1"

def test_cli_checkout_dirty_abort(tmp_path):
    """
    Verify that checkout fails and rolls back if WD is dirty.
    """
    run_deep("init", cwd=tmp_path)
    
    # Commit f1 on main
    (tmp_path / "f1.txt").write_text("v1")
    run_deep("add", "f1.txt", cwd=tmp_path)
    run_deep("commit", "-m", "init", cwd=tmp_path)
    
    # Create branch feat
    run_deep("branch", "feat", cwd=tmp_path)
    
    # Commit change to f1 on feat
    run_deep("checkout", "feat", cwd=tmp_path)
    (tmp_path / "f1.txt").write_text("feat-v1")
    run_deep("add", "f1.txt", cwd=tmp_path)
    run_deep("commit", "-m", "feat change", cwd=tmp_path)
    
    # Go back to main
    run_deep("checkout", "main", cwd=tmp_path)
    assert (tmp_path / "f1.txt").read_text() == "v1"
    
    # Now DIRTY f1.txt in main
    (tmp_path / "f1.txt").write_text("dirty-v1")
    
    # Try to checkout feat (which overwrites f1.txt)
    # This MUST fail because f1.txt is dirty.
    res = run_deep("checkout", "feat", cwd=tmp_path)
    assert res.returncode != 0
    assert "error" in res.stderr.lower() or "local changes" in res.stderr.lower()
    
    # Verify HEAD is still main and f1.txt is still dirty (not overwritten)
    dg_dir = tmp_path / ".deep"
    head_content = (dg_dir / "HEAD").read_text().strip()
    assert "ref: refs/heads/main" in head_content
    assert (tmp_path / "f1.txt").read_text() == "dirty-v1"
