import subprocess
import pytest

def run_deep(repo_dir, args):
    """Run a deep command and return the output."""
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
    run_deep(repo_dir, ["commit", "-m", "Commit 1"])

    return repo_dir

def test_diff_basic(repo):
    """Test basic diff of working tree vs index."""
    (repo / "f1.txt").write_text("v2")
    (repo / "f2.txt").write_text("new")
    
    res = run_deep(repo, ["diff"])
    assert "--- a/f1.txt" in res.stdout
    assert "+++ b/f1.txt" in res.stdout
    assert "+v2" in res.stdout
    assert "-v1" in res.stdout
    
    assert "+++ b/f2.txt" in res.stdout

def test_diff_cached(repo):
    """Test diff --cached (Index vs HEAD)."""
    (repo / "f1.txt").write_text("v2")
    res1 = run_deep(repo, ["diff", "--cached"])
    assert res1.stdout.strip() == "" # Nothing staged yet
    
    run_deep(repo, ["add", "f1.txt"])
    res2 = run_deep(repo, ["diff", "--cached"])
    assert "--- a/f1.txt" in res2.stdout
    assert "+++ b/f1.txt" in res2.stdout

def test_diff_head(repo):
    """Test diff HEAD (Working Tree vs HEAD)."""
    (repo / "f1.txt").write_text("v2")
    res = run_deep(repo, ["diff", "HEAD"])
    assert "--- a/f1.txt" in res.stdout
    assert "+++ b/f1.txt" in res.stdout
    assert "+v2" in res.stdout
    assert "-v1" in res.stdout

def test_diff_two_commits(repo):
    """Test diff C1 C2."""
    (repo / "f1.txt").write_text("v2")
    run_deep(repo, ["add", "f1.txt"])
    run_deep(repo, ["commit", "-m", "Commit 2"])
    
    res = run_deep(repo, ["diff", "HEAD~1", "HEAD"])
    assert "--- a/f1.txt" in res.stdout
    assert "+++ b/f1.txt" in res.stdout
    assert "+v2" in res.stdout

def test_diff_stat(repo):
    """Test diff --stat formatting."""
    (repo / "f1.txt").write_text("v2") # modification
    (repo / "f2.txt").write_text("new") # addition
    
    res = run_deep(repo, ["diff", "--stat"])
    assert "f1.txt" in res.stdout
    assert "f2.txt" in res.stdout
    assert "files changed" in res.stdout
