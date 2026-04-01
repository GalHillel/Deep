import subprocess
import pytest
import re

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

    # Commit 2
    (repo_dir / "f2.txt").write_text("v2")
    run_deep(repo_dir, ["add", "f2.txt"])
    run_deep(repo_dir, ["commit", "-m", "Commit 2"])

    return repo_dir

def test_show_default_head(repo):
    """Test deep show without arguments defaults to HEAD."""
    res = run_deep(repo, ["show"])
    assert "commit" in res.stdout
    assert "Commit 2" in res.stdout
    assert "diff --deep a/f2.txt b/f2.txt" in res.stdout
    assert "+v2" in res.stdout

def test_show_specific_commit(repo):
    """Test deep show with a specific commit."""
    log_res = run_deep(repo, ["log", "--oneline"])
    
    lines = [x for x in log_res.stdout.strip().split("\n") if x]
    # In Deep, log --oneline starts with the short SHA
    raw_sha_line = lines[-1]
    
    # Extract the SHA avoiding ANSI color escape codes
    clean_line = re.sub(r'\x1b\[[0-9;]*m', '', raw_sha_line)
    sha = clean_line.split(" ")[0].strip()
    
    res = run_deep(repo, ["show", sha])
    assert "commit" in res.stdout
    assert "Commit 1" in res.stdout
    assert "diff --deep a/f1.txt b/f1.txt" in res.stdout
    assert "+v1" in res.stdout
