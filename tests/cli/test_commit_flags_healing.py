import subprocess
import os
import pytest
from pathlib import Path

def get_head_sha(repo_dir: Path) -> str:
    from deep.core.repository import DEEP_DIR
    head_path = repo_dir / DEEP_DIR / "HEAD"
    if not head_path.exists():
        return ""
    content = head_path.read_text().strip()
    if content.startswith("ref:"):
        ref_path = repo_dir / DEEP_DIR / content.split(": ")[1]
        if ref_path.exists():
            return ref_path.read_text().strip()
    return content

def test_commit_all_flag(tmp_repo_with_init):
    """Verify deep commit -a stages modified tracked files but ignores untracked."""
    repo_dir = tmp_repo_with_init.parent
    
    # 1. Setup: tracked file
    f1 = repo_dir / "tracked.txt"
    f1.write_text("v1")
    subprocess.run(["deep", "add", "tracked.txt"], cwd=str(repo_dir), check=True)
    subprocess.run(["deep", "commit", "-m", "initial"], cwd=str(repo_dir), check=True)
    
    # 2. Modify tracked and create untracked
    f1.write_text("v2")
    f2 = repo_dir / "untracked.txt"
    f2.write_text("new")
    
    # 3. Commit -a
    subprocess.run(["deep", "commit", "-a", "-m", "commit all"], cwd=str(repo_dir), check=True)
    
    # 4. Verify result
    from deep.storage.objects import read_object, Commit
    from deep.core.repository import _get_tree_files
    dg_dir = tmp_repo_with_init
    head_sha = get_head_sha(repo_dir)
    commit = read_object(dg_dir / "objects", head_sha)
    files = _get_tree_files(dg_dir / "objects", commit.tree_sha)
    
    assert "tracked.txt" in files
    assert "untracked.txt" not in files, "commit -a should NOT stage untracked files"

def test_commit_allow_empty(tmp_repo_with_init):
    """Verify deep commit --allow-empty creates a commit without changes."""
    repo_dir = tmp_repo_with_init.parent
    
    # Needs at least one commit so we can test "empty relative to parent"
    f1 = repo_dir / "f1.txt"
    f1.write_text("f1")
    subprocess.run(["deep", "add", "f1.txt"], cwd=str(repo_dir), check=True)
    subprocess.run(["deep", "commit", "-m", "first"], cwd=str(repo_dir), check=True)
    
    sha1 = get_head_sha(repo_dir)
    
    # Try empty commit without flag (should fail)
    res = subprocess.run(["deep", "commit", "-m", "empty"], cwd=str(repo_dir), capture_output=True, text=True)
    assert res.returncode != 0
    assert "No changes to commit" in res.stdout or "nothing to commit" in res.stderr
    
    # Try empty commit with flag (should succeed)
    subprocess.run(["deep", "commit", "--allow-empty", "-m", "empty"], cwd=str(repo_dir), check=True)
    sha2 = get_head_sha(repo_dir)
    assert sha1 != sha2

def test_commit_amend(tmp_repo_with_init):
    """Verify deep commit --amend replaces the last commit and preserves parentage."""
    repo_dir = tmp_repo_with_init.parent
    
    # 1. Commit 1
    f1 = repo_dir / "f1.txt"
    f1.write_text("v1")
    subprocess.run(["deep", "add", "f1.txt"], cwd=str(repo_dir), check=True)
    subprocess.run(["deep", "commit", "-m", "C1"], cwd=str(repo_dir), check=True)
    c1_sha = get_head_sha(repo_dir)
    
    # 2. Commit 2
    f2 = repo_dir / "f2.txt"
    f2.write_text("v2")
    subprocess.run(["deep", "add", "f2.txt"], cwd=str(repo_dir), check=True)
    subprocess.run(["deep", "commit", "-m", "C2"], cwd=str(repo_dir), check=True)
    c2_sha = get_head_sha(repo_dir)
    
    # 3. Amend C2 with C3
    f3 = repo_dir / "f3.txt"
    f3.write_text("v3")
    subprocess.run(["deep", "add", "f3.txt"], cwd=str(repo_dir), check=True)
    subprocess.run(["deep", "commit", "--amend", "-m", "C3"], cwd=str(repo_dir), check=True)
    c3_sha = get_head_sha(repo_dir)
    
    assert c3_sha != c2_sha
    
    # 4. Verify C3 parents. C3 should have C1 as parent (same as C2).
    from deep.storage.objects import read_object, Commit
    dg_dir = tmp_repo_with_init
    commit3 = read_object(dg_dir / "objects", c3_sha)
    assert c1_sha in commit3.parent_shas
    assert c2_sha not in commit3.parent_shas

def test_commit_sign_flag(tmp_repo_with_init):
    """Verify deep commit -S adds a signature header."""
    repo_dir = tmp_repo_with_init.parent
    
    f1 = repo_dir / "f1.txt"
    f1.write_text("v1")
    subprocess.run(["deep", "add", "f1.txt"], cwd=str(repo_dir), check=True)
    subprocess.run(["deep", "commit", "-S", "-m", "signed"], cwd=str(repo_dir), check=True)
    
    sha = get_head_sha(repo_dir)
    from deep.storage.objects import read_object
    commit = read_object(tmp_repo_with_init / "objects", sha)
    assert commit.signature is not None
    assert commit.signature.startswith("SIG:")

def test_commit_amend_empty_fail(tmp_repo_with_init):
    """Verify deep commit --amend fails on empty repo."""
    repo_dir = tmp_repo_with_init.parent
    res = subprocess.run(["deep", "commit", "--amend", "-m", "fail"], cwd=str(repo_dir), capture_output=True, text=True)
    assert res.returncode != 0
    assert "nothing to amend" in res.stderr.lower()

@pytest.fixture
def tmp_repo_with_init(tmp_repo):
    repo_dir = tmp_repo.parent
    subprocess.run(["deep", "init"], cwd=str(repo_dir), check=True, capture_output=True)
    return tmp_repo
