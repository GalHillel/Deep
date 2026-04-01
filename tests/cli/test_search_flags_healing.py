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

    # Commit 1
    (repo_dir / "f1.txt").write_text("Hello World\nTODO: fix this")
    run_deep(repo_dir, ["add", "f1.txt"])
    run_deep(repo_dir, ["commit", "-m", "Initial commit"])

    # Commit 2
    (repo_dir / "f2.txt").write_text("Regex test 123\nfixed: bug")
    run_deep(repo_dir, ["add", "f2.txt"])
    run_deep(repo_dir, ["commit", "-m", "Second commit"])

    return repo_dir

def test_search_literal(repo):
    """Test searching for a literal string."""
    res = run_deep(repo, ["search", "TODO"])
    assert res.returncode == 0
    assert "f1.txt:2: TODO: fix this" in res.stdout
    assert "Found 2 match" in res.stdout

def test_search_regex(repo):
    """Test searching with a regular expression."""
    res = run_deep(repo, ["search", "^fixed:"])
    assert res.returncode == 0
    assert "f2.txt:2: fixed: bug" in res.stdout
    assert "Found 1 match" in res.stdout

def test_search_no_match(repo):
    """Test searching for something that doesn't exist."""
    res = run_deep(repo, ["search", "MISSING_STRING"])
    assert res.returncode == 0
    assert "No matches found" in res.stdout

def test_search_history(repo):
    """Test search finds content from old commits."""
    # Modify f1.txt in commit 3
    (repo / "f1.txt").write_text("New content")
    run_deep(repo, ["add", "f1.txt"])
    run_deep(repo, ["commit", "-m", "Third commit"])

    # Search for "TODO" which only existed in previous commits
    res = run_deep(repo, ["search", "TODO"])
    assert res.returncode == 0
    assert "f1.txt:2: TODO: fix this" in res.stdout
    # It should show it from the first two commits (if it hasn't changed in the second)
    # Actually, Commit 1 and Commit 2 both have TODO in f1.txt.
    # So it should find at least 2 matches.
    assert "Found 2 match" in res.stdout
