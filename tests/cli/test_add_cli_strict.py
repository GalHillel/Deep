import subprocess
import os
import time
import pytest
import multiprocessing
import sys
from pathlib import Path
from deep.storage.index import read_index

def worker_add_cli(repo_dir, file_name):
    """Worker that runs 'deep add' via subprocess."""
    try:
        # We assume 'deep' is in the PATH or we use sys.executable + wrapper
        # For this test, we'll try to run it as a module or if deep.cmd is available.
        # But per user rules: run_command(["deep", "add", ...])
        
        # Create unique file
        file_path = repo_dir / file_name
        file_path.write_text(f"content of {file_name}")
        
        # Run deep add
        subprocess.run(["deep", "add", file_name], cwd=str(repo_dir), check=True, capture_output=True)
        return True
    except Exception:
        return False

def test_cli_add_single(tmp_repo_with_init):
    """
    STRICT CASE 1: Single file add via CLI.
    """
    dg_dir = tmp_repo_with_init
    repo_dir = dg_dir.parent
    
    file_name = "test_single.txt"
    file_path = repo_dir / file_name
    file_path.write_text("hello deep")
    
    # Run CLI
    result = subprocess.run(["deep", "add", file_name], cwd=str(repo_dir), capture_output=True, text=True)
    assert result.returncode == 0, f"CLI failed: {result.stderr}"
    
    # Verify index
    index = read_index(dg_dir)
    assert file_name in index.entries
    assert index.entries[file_name].size == len("hello deep")

def test_cli_add_multiple(tmp_repo_with_init):
    """
    STRICT CASE 2: Multiple files add via CLI.
    """
    dg_dir = tmp_repo_with_init
    repo_dir = dg_dir.parent
    
    files = ["f1.txt", "f2.txt"]
    for f in files:
        (repo_dir / f).write_text(f"content_{f}")
        
    result = subprocess.run(["deep", "add"] + files, cwd=str(repo_dir), capture_output=True, text=True)
    assert result.returncode == 0
    
    index = read_index(dg_dir)
    for f in files:
        assert f in index.entries

def test_cli_add_missing_file(tmp_repo_with_init):
    """
    STRICT CASE 3: Adding a missing file MUST fail and ROLLBACK.
    """
    dg_dir = tmp_repo_with_init
    repo_dir = dg_dir.parent
    
    # Start with a clean index
    index_before = read_index(dg_dir)
    assert len(index_before.entries) == 0
    
    # Try adding a file that doesn't exist
    result = subprocess.run(["deep", "add", "non_existent.txt"], cwd=str(repo_dir), capture_output=True, text=True)
    assert result.returncode != 0
    assert "error" in result.stderr.lower()
    
    # Verify index is still empty (No partial state leaked)
    index_after = read_index(dg_dir)
    assert len(index_after.entries) == 0, "Index should remain unchanged after failed add"

def test_cli_add_concurrent(tmp_repo_with_init):
    """
    STRICT CASE 4: Concurrent 'deep add' processes.
    RepoLock should handle queuing. 
    """
    dg_dir = tmp_repo_with_init
    repo_dir = dg_dir.parent
    
    num_workers = 4
    processes = []
    
    # Use a pool or manual processes to run CLI simultaneously
    import concurrent.futures
    
    with concurrent.futures.ProcessPoolExecutor(max_workers=num_workers) as executor:
        futures = []
        for i in range(num_workers):
            f_name = f"concurrent_{i}.txt"
            futures.append(executor.submit(worker_add_cli, repo_dir, f_name))
            
        results = [f.result() for f in futures]
    
    assert all(results), "All concurrent adds should have succeeded"
    
    # Verify all files in index
    index = read_index(dg_dir)
    for i in range(num_workers):
        assert f"concurrent_{i}.txt" in index.entries

@pytest.fixture
def tmp_repo_with_init(tmp_repo):
    """Fixture that provides an initialized deep repo."""
    # tmp_repo is already a dg_dir (.deep)
    repo_dir = tmp_repo.parent
    subprocess.run(["deep", "init"], cwd=str(repo_dir), check=True, capture_output=True)
    return tmp_repo
