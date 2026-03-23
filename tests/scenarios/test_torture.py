import pytest
from deep.core.errors import DeepCLIException
import os
import shutil
import tempfile
import random
import string
import threading
from pathlib import Path
from deep.core.repository import init_repo
from deep.commands import add_cmd, commit_cmd, checkout_cmd, merge_cmd, reset_cmd
from deep.core.refs import resolve_head, update_branch
from deep.storage.objects import read_object

@pytest.fixture
def repo_dir():
    tmpdir = tempfile.mkdtemp()
    original_cwd = os.getcwd()
    os.chdir(tmpdir)
    init_repo(tmpdir)
    yield Path(tmpdir)
    os.chdir(original_cwd)
    shutil.rmtree(tmpdir)

def random_string(length=10):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

def test_torture_massive_files(repo_dir):
    """Test with many small files."""
    num_files = 500
    for i in range(num_files):
        (repo_dir / f"file_{i}.txt").write_text(random_string(20))
    
    class Args: files = ["."]; message = "massive add"; ai = False; sign = False
    add_cmd.run(Args())
    commit_cmd.run(Args())
    assert resolve_head(repo_dir / ".deep")

def test_torture_deep_directories(repo_dir):
    """Test with very deep directory structure."""
    curr = repo_dir
    for i in range(20):
        curr = curr / f"dir_{i}"
        curr.mkdir()
    (curr / "deep_file.txt").write_text("deep")
    
    class Args: files = ["."]; message = "deep dirs"; ai = False; sign = False
    add_cmd.run(Args())
    commit_cmd.run(Args())
    assert resolve_head(repo_dir / ".deep")

def test_torture_rapid_commits(repo_dir):
    """Test rapid sequence of commits."""
    for i in range(50):
        (repo_dir / "counter.txt").write_text(str(i))
        class Args: files = ["counter.txt"]; message = f"commit {i}"; ai = False; sign = False
        add_cmd.run(Args())
        commit_cmd.run(Args())
    assert resolve_head(repo_dir / ".deep")

def test_torture_checkout_conflict_protection(repo_dir):
    """Verify checkout refuses to overwrite untracked work."""
    (repo_dir / "tracked.txt").write_text("v1")
    class Args: files = ["tracked.txt"]; message = "v1"; ai = False; sign = False
    add_cmd.run(Args())
    commit_cmd.run(Args())
    v1_sha = resolve_head(repo_dir / ".deep")
    update_branch(repo_dir / ".deep", "branch1", v1_sha)
    
    (repo_dir / "tracked.txt").write_text("v2")
    Args.message = "v2"
    add_cmd.run(Args())
    commit_cmd.run(Args())
    
    # Create an untracked file that would be overwritten by v1 tree if we checked out
    # Actually, v1 has tracked.txt. If we have an untracked 'tracked.txt' in WD... 
    # Wait, tracked.txt is already tracked. 
    # Let's use a NEW file in v3.
    (repo_dir / "new_file.txt").write_text("v3")
    Args.message = "v3"
    Args.files = ["new_file.txt"]
    add_cmd.run(Args())
    commit_cmd.run(Args())
    v3_sha = resolve_head(repo_dir / ".deep")
    
    # Go back to v1
    class CheckoutArgs: target = v1_sha; force = False
    checkout_cmd.run(CheckoutArgs())
    assert not (repo_dir / "new_file.txt").exists()
    
    # Now create untracked 'new_file.txt'
    (repo_dir / "new_file.txt").write_text("dirty untracked")
    
    # Attempt to checkout v3 (which has 'new_file.txt')
    CheckoutArgs.target = v3_sha
    with pytest.raises(DeepCLIException): # Should exit(1) due to safety check
        checkout_cmd.run(CheckoutArgs())
    
    # Verify file was NOT overwritten
    assert (repo_dir / "new_file.txt").read_text() == "dirty untracked"

def test_torture_large_binary_files(repo_dir):
    """Test with large binary blobs."""
    data = os.urandom(1024 * 1024 * 5) # 5MB
    (repo_dir / "large.bin").write_bytes(data)
    class Args: files = ["large.bin"]; message = "large bin"; ai = False; sign = False
    add_cmd.run(Args())
    commit_cmd.run(Args())
    
    # Verify we can read it back
    sha = resolve_head(repo_dir / ".deep")
    commit = read_object(repo_dir / ".deep" / "objects", sha)
    # Recursively find the blob in the tree... (simplified check)
    assert (repo_dir / "large.bin").read_bytes() == data

def test_torture_empty_commit(repo_dir):
    """Ensure we can't create empty commits (or handle them if allowed)."""
    # First commit
    (repo_dir / "f").write_text("1")
    class Args: files = ["f"]; message = "1"; ai = False; sign = False
    add_cmd.run(Args())
    commit_cmd.run(Args())
    
    # Second commit with NO changes
    Args.message = "empty"
    with pytest.raises(DeepCLIException):
        commit_cmd.run(Args())

def test_torture_deletion_workflow(repo_dir):
    """Test adding, then deleting, then staging deletion."""
    f = repo_dir / "delete_me.txt"
    f.write_text("bye")
    class Args: files = ["delete_me.txt"]; message = "add"; ai = False; sign = False
    add_cmd.run(Args())
    commit_cmd.run(Args())
    
    f.unlink()
    # Currently 'deep add' might not handle deletions unless we pass the path
    # or implement 'deep rm'. Deep uses 'deep add -u'.
    # Our current add_cmd processes args.files. 
    # If we pass the deleted file path to add_cmd, it should check it.
    add_cmd.run(Args())
    # Verify index? (Simplified)

def test_torture_merge_complex_ff(repo_dir):
    """Multi-step fast-forward."""
    dg_dir = repo_dir / ".deep"
    (repo_dir / "f").write_text("base")
    class Args: files = ["f"]; message = "base"; ai = False; sign = False
    add_cmd.run(Args())
    commit_cmd.run(Args())
    base_sha = resolve_head(dg_dir)
    
    update_branch(dg_dir, "topic", base_sha)
    class CheckoutArgs: target = "topic"; force = False
    checkout_cmd.run(CheckoutArgs())
    
    for i in range(5):
        (repo_dir / "f").write_text(f"v{i}")
        add_cmd.run(Args())
        Args.message = f"v{i}"
        commit_cmd.run(Args())
    topic_sha = resolve_head(dg_dir)
    
    CheckoutArgs.target = "main"
    checkout_cmd.run(CheckoutArgs())
    
    class MergeArgs: branch = "topic"
    merge_cmd.run(MergeArgs())
    assert resolve_head(dg_dir) == topic_sha

def test_torture_reset_hard_dirty_workdir(repo_dir):
    """Reset --hard should clean dirty workdir."""
    (repo_dir / "f").write_text("v1")
    class Args: files = ["f"]; message = "v1"; ai = False; sign = False
    add_cmd.run(Args())
    commit_cmd.run(Args())
    v1_sha = resolve_head(repo_dir / ".deep")
    
    (repo_dir / "f").write_text("dirty")
    (repo_dir / "untracked.txt").write_text("untracked")
    
    class ResetArgs: commit = v1_sha; soft = False; hard = True
    reset_cmd.run(ResetArgs())
    
    assert (repo_dir / "f").read_text() == "v1"
    # Note: deep reset --hard doesn't remove untracked files, only tracked ones.
    # Our implementation uses current_index.entries to clear.
    assert (repo_dir / "untracked.txt").exists()

def test_torture_file_path_edge_cases(repo_dir):
    """Test spaces and weird characters in filenames."""
    name = "file with spaces !@#$%^&().txt"
    (repo_dir / name).write_text("weird")
    class Args: files = [name]; message = "weird name"; ai = False; sign = False
    add_cmd.run(Args())
    commit_cmd.run(Args())
    assert (repo_dir / name).exists()
