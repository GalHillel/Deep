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

    # Commit 2
    (repo_dir / "f2.txt").write_text("v1")
    run_deep(repo_dir, ["add", "f2.txt"])
    run_deep(repo_dir, ["commit", "-m", "Commit 2"])

    # Branch feature
    run_deep(repo_dir, ["branch", "feature"])
    
    # Commit 3 (on main)
    (repo_dir / "f3.txt").write_text("v1")
    run_deep(repo_dir, ["add", "f3.txt"])
    run_deep(repo_dir, ["commit", "-m", "Commit 3"])

    # Checkout feature
    run_deep(repo_dir, ["checkout", "feature"])
    
    # Commit 4 (on feature)
    (repo_dir / "f4.txt").write_text("v1")
    run_deep(repo_dir, ["add", "f4.txt"])
    run_deep(repo_dir, ["commit", "-m", "Commit 4"])

    return repo_dir

def test_log_basic(repo):
    res = run_deep(repo, ["log"])
    assert "Commit 4" in res.stdout
    assert "Commit 2" in res.stdout
    assert "Commit 1" in res.stdout
    assert "Commit 3" not in res.stdout

def test_log_oneline(repo):
    res = run_deep(repo, ["log", "--oneline"])
    lines = [x for x in res.stdout.strip().split("\n") if x]
    assert len(lines) == 3
    assert "Commit 4" in lines[0]
    assert "Commit 2" in lines[1]
    assert "Commit 1" in lines[2]

def test_log_max_count(repo):
    res = run_deep(repo, ["log", "-n", "2"])
    assert "Commit 4" in res.stdout
    assert "Commit 2" in res.stdout
    assert "Commit 1" not in res.stdout

def test_log_graph(repo):
    res = run_deep(repo, ["log", "--graph"])
    assert "●" in res.stdout
    assert "│" in res.stdout

def test_log_range(repo):
    res = run_deep(repo, ["log", "main..feature"])
    assert "Commit 4" in res.stdout
    assert "Commit 3" not in res.stdout
    assert "Commit 2" not in res.stdout
    assert "Commit 1" not in res.stdout

def test_log_range_reverse(repo):
    res = run_deep(repo, ["log", "feature..main"])
    assert "Commit 3" in res.stdout
    assert "Commit 4" not in res.stdout
    assert "Commit 2" not in res.stdout
