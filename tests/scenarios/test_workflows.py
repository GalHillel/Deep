import pytest
import os
import shutil
import tempfile
from pathlib import Path
from deep.core.repository import init_repo, find_repo
from deep.commands import add_cmd, commit_cmd, checkout_cmd, merge_cmd, reset_cmd, status_cmd
from deep.storage.index import read_index, DeepIndex, DeepIndexEntry
from deep.core.status import compute_status
from deep.core.refs import resolve_head, update_branch, get_current_branch

@pytest.fixture
def repo_dir():
    tmpdir = tempfile.mkdtemp()
    original_cwd = os.getcwd()
    os.chdir(tmpdir)
    init_repo(tmpdir)
    yield Path(tmpdir)
    os.chdir(original_cwd)
    from deep.utils.logger import shutdown_logging
    shutdown_logging()
    shutil.rmtree(tmpdir)

def test_basic_workflow(repo_dir):
    # 1. Add and commit
    file1 = repo_dir / "file1.txt"
    file1.write_text("hello")
    
    class Args:
        files = ["file1.txt"]
        message = "initial commit"
        ai = False
        sign = False
    
    add_cmd.run(Args())
    commit_cmd.run(Args())
    
    status = compute_status(repo_dir)
    assert len(status.staged_new) == 0
    assert len(status.modified) == 0
    
    # 2. Modify and stage
    file1.write_text("hello world")
    add_cmd.run(Args())
    
    status = compute_status(repo_dir)
    assert len(status.staged_modified) == 1
    
    # 2.5 Commit staged changes so checkout is safe
    Args.message = "second commit"
    commit_cmd.run(Args())
    
    # 3. Branch and checkout
    class BranchArgs:
        target = "feature"
        force = False
    
    # Create branch (manually for now since no branch_cmd.run shown yet, 
    # but we can simulate by updating refs/heads)
    dg_dir = repo_dir / ".deep"
    head_sha = resolve_head(dg_dir)
    update_branch(dg_dir, "feature", head_sha)
    
    checkout_cmd.run(BranchArgs())
    
    assert get_current_branch(dg_dir) == "feature"

def test_reset_modes(repo_dir):
    file1 = repo_dir / "file1.txt"
    file1.write_text("v1")
    
    class Args:
        files = ["file1.txt"]
        message = "v1"
        ai = False
        sign = False
    
    add_cmd.run(Args())
    commit_cmd.run(Args())
    v1_sha = resolve_head(repo_dir / ".deep")
    
    file1.write_text("v2")
    Args.message = "v2"
    add_cmd.run(Args())
    commit_cmd.run(Args())
    v2_sha = resolve_head(repo_dir / ".deep")
    
    # Reset --soft
    class ResetArgs:
        commit = v1_sha
        soft = True
        hard = False
    reset_cmd.run(ResetArgs())
    assert resolve_head(repo_dir / ".deep") == v1_sha
    assert (repo_dir / "file1.txt").read_text() == "v2" # workdir kept
    
    # Reset --hard
    ResetArgs.commit = v2_sha
    ResetArgs.soft = False
    ResetArgs.hard = True
    reset_cmd.run(ResetArgs())
    assert resolve_head(repo_dir / ".deep") == v2_sha
    assert (repo_dir / "file1.txt").read_text() == "v2"

def test_merge_fast_forward(repo_dir):
    file1 = repo_dir / "file1.txt"
    file1.write_text("base")
    
    class Args:
        files = ["file1.txt"]
        message = "base"
        ai = False
        sign = False
    
    add_cmd.run(Args())
    commit_cmd.run(Args())
    base_sha = resolve_head(repo_dir / ".deep")
    
    # Create branch
    dg_dir = repo_dir / ".deep"
    from deep.core.refs import update_branch
    update_branch(dg_dir, "dev", base_sha)
    
    # Modify on dev
    class CheckoutArgs: target = "dev"; force = False
    checkout_cmd.run(CheckoutArgs())
    
    file1.write_text("dev change")
    add_cmd.run(Args())
    Args.message = "dev commit"
    commit_cmd.run(Args())
    dev_sha = resolve_head(dg_dir)
    
    # Switch back to main and merge dev
    CheckoutArgs.target = "main"
    checkout_cmd.run(CheckoutArgs())
    
    class MergeArgs: branch = "dev"
    merge_cmd.run(MergeArgs())
    
    assert resolve_head(dg_dir) == dev_sha
    assert (repo_dir / "file1.txt").read_text() == "dev change"
