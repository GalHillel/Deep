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
    (repo_dir / "f1.txt").write_text("v2")
    run_deep(repo_dir, ["add", "f1.txt"])
    run_deep(repo_dir, ["commit", "-m", "Commit 2"])

    return repo_dir

def test_graph_basic(repo):
    """Test basic graph output."""
    res = run_deep(repo, ["graph"])
    assert "●" in res.stdout
    assert "Commit 2" in res.stdout
    assert "Commit 1" in res.stdout
    assert "HEAD" in res.stdout

def test_graph_max_count(repo):
    """Test graph -n/--max-count."""
    # Commit 3
    (repo / "f1.txt").write_text("v3")
    run_deep(repo, ["add", "f1.txt"])
    run_deep(repo, ["commit", "-m", "Commit 3"])

    # Limit to 1
    res1 = run_deep(repo, ["graph", "-n", "1"])
    assert "Commit 3" in res1.stdout
    assert "Commit 2" not in res1.stdout
    
    # Limit to 2
    res2 = run_deep(repo, ["graph", "-n", "2"])
    assert "Commit 3" in res2.stdout
    assert "Commit 2" in res2.stdout
    assert "Commit 1" not in res2.stdout

def test_graph_all(repo):
    """Test graph --all with multiple branches."""
    # Create another branch
    run_deep(repo, ["branch", "feat"])
    run_deep(repo, ["checkout", "feat"])
    (repo / "f2.txt").write_text("feat")
    run_deep(repo, ["add", "f2.txt"])
    run_deep(repo, ["commit", "-m", "Feat commit"])

    # Standard graph (current branch only)
    res_std = run_deep(repo, ["graph"])
    assert "Feat commit" in res_std.stdout
    # Commit 2 is a parent, so it might be there, but let's check another branch tip
    
    run_deep(repo, ["checkout", "main"])
    res_master = run_deep(repo, ["graph"])
    assert "Commit 2" in res_master.stdout
    assert "Feat commit" not in res_master.stdout

    # Graph --all
    res_all = run_deep(repo, ["graph", "--all"])
    assert "Commit 2" in res_all.stdout
    assert "Feat commit" in res_all.stdout
    assert "feat" in res_all.stdout
    assert "main" in res_all.stdout
