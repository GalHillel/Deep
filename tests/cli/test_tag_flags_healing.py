import subprocess
import pytest
from pathlib import Path

def run_deep(repo_dir, args):
    """Run a deep command and return the result."""
    result = subprocess.run(
        ["deep"] + args,
        cwd=repo_dir,
        capture_output=True,
        text=True
    )
    return result

@pytest.fixture
def repo(tmp_path):
    repo_dir = tmp_path / "test_repo"
    repo_dir.mkdir()
    run_deep(repo_dir, ["init"])
    
    # Commit 1
    (repo_dir / "f1.txt").write_text("v1")
    run_deep(repo_dir, ["add", "f1.txt"])
    run_deep(repo_dir, ["commit", "-m", "Initial commit"])
    
    return repo_dir

def test_tag_list_empty(repo):
    """Test listing tags when none exist."""
    res = run_deep(repo, ["tag"])
    assert res.returncode == 0
    assert res.stdout.strip() == ""

def test_tag_create_lightweight(repo):
    """Test creating a lightweight tag."""
    res = run_deep(repo, ["tag", "v1.0"])
    assert res.returncode == 0
    
    res_list = run_deep(repo, ["tag"])
    assert "v1.0" in res_list.stdout

def test_tag_create_annotated(repo):
    """Test creating an annotated tag."""
    res = run_deep(repo, ["tag", "-a", "v1.1", "-m", "Release 1.1"])
    assert res.returncode == 0
    
    res_list = run_deep(repo, ["tag"])
    assert "v1.1" in res_list.stdout
    
    # Verify it's an annotated tag by showing it
    res_show = run_deep(repo, ["show", "v1.1"])
    assert "tag v1.1" in res_show.stdout
    assert "Tagger:" in res_show.stdout
    assert "Release 1.1" in res_show.stdout

def test_tag_create_annotated_no_m(repo):
    """Test creating an annotated tag without -m."""
    res = run_deep(repo, ["tag", "-a", "v1.2"])
    assert res.returncode == 0
    
    res_show = run_deep(repo, ["show", "v1.2"])
    assert "tag v1.2" in res_show.stdout
    assert "Annotated tag v1.2" in res_show.stdout

def test_tag_delete(repo):
    """Test deleting a tag."""
    run_deep(repo, ["tag", "v2.0"])
    
    res_del = run_deep(repo, ["tag", "-d", "v2.0"])
    assert res_del.returncode == 0
    assert "Deleted tag 'v2.0'" in res_del.stdout
    
    res_list = run_deep(repo, ["tag"])
    assert "v2.0" not in res_list.stdout

def test_tag_delete_nonexistent(repo):
    """Test deleting a tag that doesn't exist."""
    res = run_deep(repo, ["tag", "-d", "non-existent"])
    assert res.returncode != 0
    assert "not found" in res.stderr

def test_tag_create_duplicate(repo):
    """Test creating a tag that already exists."""
    run_deep(repo, ["tag", "v3.0"])
    res = run_deep(repo, ["tag", "v3.0"])
    assert res.returncode != 0
    assert "already exists" in res.stderr
