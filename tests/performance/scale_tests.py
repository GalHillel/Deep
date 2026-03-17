import pytest
import os
import shutil
import tempfile
import time
from pathlib import Path
from deep.core.repository import init_repo,DEEP_DIR
from deep.commands import add_cmd, commit_cmd, branch_cmd, status_cmd, log_cmd, diff_cmd

class SafeArgs:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

@pytest.fixture
def repo_dir():
    tmpdir = tempfile.mkdtemp(prefix="deep_scale_")
    original_cwd = os.getcwd()
    os.chdir(tmpdir)
    init_repo(tmpdir)
    yield Path(tmpdir)
    os.chdir(original_cwd)
    # Windows cleanup
    import stat
    def on_rm_error(func, p, exc_info):
        os.chmod(p, stat.S_IWRITE)
        func(p)
    shutil.rmtree(tmpdir, onerror=on_rm_error)

def test_scale_massive_files_10k(repo_dir):
    """Test correctly staging and committing 10,000 files."""
    num_files = 10000
    print(f"\nCreating {num_files} files...")
    for i in range(num_files):
        # Batching creation in subdirs to avoid extreme root listing slowdown
        subdir = repo_dir / f"dir_{i // 100}"
        subdir.mkdir(exist_ok=True)
        (subdir / f"file_{i}.txt").write_text(f"content {i}")
    
    start = time.perf_counter()
    add_cmd.run(SafeArgs(files=["."], ai=False, sign=False))
    add_time = time.perf_counter() - start
    print(f"Add 10k files: {add_time:.2f}s")
    
    start = time.perf_counter()
    commit_cmd.run(SafeArgs(message="10k commit", ai=False, sign=False))
    commit_time = time.perf_counter() - start
    print(f"Commit 10k files: {commit_time:.2f}s")
    
    # Verify status is clean
    start = time.perf_counter()
    # status_cmd.run prints to stdout, we just want to ensure it doesn't crash
    status_cmd.run(SafeArgs(porcelain=True))
    status_time = time.perf_counter() - start
    print(f"Status check time: {status_time:.2f}s")

def test_scale_massive_branches_1k(repo_dir):
    """Test creating and listing 1,000 branches."""
    # First commit
    (repo_dir / "f").write_text("base")
    add_cmd.run(SafeArgs(files=["."], ai=False, sign=False))
    commit_cmd.run(SafeArgs(message="base", ai=False, sign=False))
    
    num_branches = 1000
    print(f"\nCreating {num_branches} branches...")
    start = time.perf_counter()
    for i in range(num_branches):
        branch_cmd.run(SafeArgs(name=f"branch_{i}", start_point="HEAD"))
    create_time = time.perf_counter() - start
    print(f"Create 1k branches: {create_time:.2f}s")
    
    # List branches
    start = time.perf_counter()
    branch_cmd.run(SafeArgs(name=None))
    list_time = time.perf_counter() - start
    print(f"List 1k branches: {list_time:.2f}s")

def test_scale_deep_dag_log(repo_dir):
    """Test logging on a deep DAG (1,000 sequential commits)."""
    num_commits = 1000
    print(f"\nCreating {num_commits} commits...")
    start = time.perf_counter()
    for i in range(num_commits):
        (repo_dir / "counter.txt").write_text(str(i))
        add_cmd.run(SafeArgs(files=["counter.txt"], ai=False, sign=False))
        commit_cmd.run(SafeArgs(message=f"commit {i}", ai=False, sign=False))
    seq_time = time.perf_counter() - start
    print(f"Create 1k sequential commits: {seq_time:.2f}s")
    
    # Run log
    start = time.perf_counter()
    log_cmd.run(SafeArgs(max_count=None, graph=False, oneline=True))
    log_time = time.perf_counter() - start
    print(f"Log 1k commits: {log_time:.2f}s")
