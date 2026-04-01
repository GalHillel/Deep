import subprocess
import pytest
import os

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

    # File in root
    (repo_dir / "f1.txt").write_text("root file")
    run_deep(repo_dir, ["add", "f1.txt"])

    # File in sub-directory
    sub_dir = repo_dir / "subdir"
    sub_dir.mkdir()
    (sub_dir / "f2.txt").write_text("sub file")
    run_deep(repo_dir, ["add", "subdir/f2.txt"])

    run_deep(repo_dir, ["commit", "-m", "Initial commit"])

    return repo_dir

def test_ls_tree_basic(repo):
    """Test basic ls-tree output (non-recursive)."""
    res = run_deep(repo, ["ls-tree", "HEAD"])
    assert res.returncode == 0
    # Should show f1.txt and subdir
    assert "100644 blob" in res.stdout
    assert "f1.txt" in res.stdout
    assert "040000 tree" in res.stdout
    assert "subdir" in res.stdout
    # Should NOT show f2.txt (non-recursive)
    assert "f2.txt" not in res.stdout

def test_ls_tree_recursive(repo):
    """Test recursive ls-tree output."""
    res = run_deep(repo, ["ls-tree", "-r", "HEAD"])
    assert res.returncode == 0
    # Should show subdir AND f2.txt
    assert "040000 tree" in res.stdout
    assert "subdir" in res.stdout
    assert "subdir/f2.txt" in res.stdout
    assert "100644 blob" in res.stdout

def test_ls_tree_formatting(repo):
    """Test that ls-tree uses tab separator exactly like Git."""
    res = run_deep(repo, ["ls-tree", "HEAD"])
    assert res.returncode == 0
    # Search for "<sha><tab>f1.txt"
    # f1.txt check
    lines = res.stdout.splitlines()
    f1_line = [l for l in lines if "f1.txt" in l][0]
    # format: <mode> <type> <sha>\t<path>
    parts = f1_line.split()
    sha = parts[2]
    assert f"{sha}\tf1.txt" in f1_line

def test_ls_tree_invalid_revision(repo):
    """Test error message for invalid revision."""
    res = run_deep(repo, ["ls-tree", "non-existent-sha"])
    assert res.returncode != 0
    assert "revision 'non-existent-sha' not found" in res.stderr
