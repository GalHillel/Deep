from pathlib import Path
import tempfile
import shutil
import pytest

def test_init_variants(repo_factory):
    """Test init with --bare and other options."""
    # Standard init
    path = repo_factory.create("standard")
    assert (path / ".deep").exists()
    
    # Bare init
    bare_path = Path(tempfile.mkdtemp())
    res = repo_factory.run(["init", "--bare"], cwd=bare_path)
    assert res.returncode == 0
    assert (bare_path / "objects").exists()
    assert not (bare_path / ".deep").exists()
    shutil.rmtree(bare_path)

def test_add_and_commit_options(repo_factory):
    path = repo_factory.create()
    (path / "file1.txt").write_text("v1")
    (path / "file2.txt").write_text("v2")
    
    # Add with glob-like behavior (CLI only)
    repo_factory.run(["add", "."], cwd=path)
    
    # Commit with --sign and --all
    res = repo_factory.run(["commit", "-m", "initial", "--sign", "--all"], cwd=path)
    assert res.returncode == 0
    
    # Amend commit
    (path / "file1.txt").write_text("v1-amended")
    repo_factory.run(["add", "file1.txt"], cwd=path)
    res = repo_factory.run(["commit", "--amend", "-m", "amended commit"], cwd=path)
    assert res.returncode == 0
    assert "amended commit" in repo_factory.run(["log", "-n", "1"], cwd=path).stdout
    
    # Commit with --allow-empty
    res = repo_factory.run(["commit", "--allow-empty", "-m", "empty commit"], cwd=path)
    assert res.returncode == 0

def test_basic_flow_repetition(repo_factory):
    """Run init -> add -> commit -> status -> log 10 times."""
    for i in range(10):
        path = repo_factory.create(f"basic_flow_{i}")
        (path / "file.txt").write_text(f"content {i}")
        repo_factory.run(["add", "file.txt"], cwd=path)
        repo_factory.run(["commit", "-m", f"commit {i}"], cwd=path)
        
        res = repo_factory.run(["status"], cwd=path)
        assert "clean" in res.stdout.lower() or "nothing" in res.stdout.lower()
        
        res = repo_factory.run(["log"], cwd=path)
        assert f"commit {i}" in res.stdout

def test_branch_checkout_merge(repo_factory):
    """Test branch, checkout, and merge flow."""
    path = repo_factory.create()
    (path / "master.txt").write_text("master")
    repo_factory.run(["add", "master.txt"], cwd=path)
    repo_factory.run(["commit", "-m", "initial"], cwd=path)
    
    # Branch and Checkout
    repo_factory.run(["branch", "feat"], cwd=path)
    repo_factory.run(["checkout", "feat"], cwd=path)
    
    (path / "feat.txt").write_text("feature")
    repo_factory.run(["add", "feat.txt"], cwd=path)
    repo_factory.run(["commit", "-m", "feature commit"], cwd=path)
    
    # Merge
    repo_factory.run(["checkout", "main"], cwd=path)
    res = repo_factory.run(["merge", "feat"], cwd=path)
    assert res.returncode == 0
    assert (path / "feat.txt").exists()

def test_branch_and_checkout_advanced(repo_factory):
    path = repo_factory.create()
    (path / "f.txt").write_text("main")
    repo_factory.run(["add", "f.txt"], cwd=path)
    repo_factory.run(["commit", "-m", "main"], cwd=path)
    
    # Checkout -b
    res = repo_factory.run(["checkout", "-b", "feature/new"], cwd=path)
    assert res.returncode == 0
    assert "feature/new" in repo_factory.run(["branch"], cwd=path).stdout
    
    # Tagging
    repo_factory.run(["tag", "-a", "v1.0", "-m", "Release 1.0"], cwd=path)
    assert "v1.0" in repo_factory.run(["tag"], cwd=path).stdout

def test_rm_mv_reset(repo_factory):
    path = repo_factory.create()
    (path / "a.txt").write_text("A")
    repo_factory.run(["add", "a.txt"], cwd=path)
    repo_factory.run(["commit", "-m", "initial"], cwd=path)
    
    # MV
    repo_factory.run(["mv", "a.txt", "b.txt"], cwd=path)
    assert not (path / "a.txt").exists()
    assert (path / "b.txt").exists()
    
    # RM
    repo_factory.run(["rm", "b.txt"], cwd=path)
    assert not (path / "b.txt").exists()
    
    # RESET
    repo_factory.run(["reset", "--hard", "HEAD"], cwd=path)
    assert (path / ".deep").exists()

def test_rebase_and_stash(repo_factory):
    path = repo_factory.create()
    (path / "f.txt").write_text("v1")
    repo_factory.run(["add", "f.txt"], cwd=path)
    repo_factory.run(["commit", "-m", "v1"], cwd=path)
    
    # Stash
    (path / "f.txt").write_text("dirty")
    repo_factory.run(["stash", "push"], cwd=path)
    assert "dirty" not in (path / "f.txt").read_text()
    repo_factory.run(["stash", "pop"], cwd=path)
    assert "dirty" in (path / "f.txt").read_text()
    
    # Rebase
    repo_factory.run(["commit", "-a", "-m", "dirty commit"], cwd=path)
    repo_factory.run(["checkout", "-b", "topic"], cwd=path)
    (path / "topic.txt").write_text("topic")
    repo_factory.run(["add", "topic.txt"], cwd=path)
    repo_factory.run(["commit", "-m", "topic"], cwd=path)
    
    repo_factory.run(["checkout", "main"], cwd=path)
    (path / "main2.txt").write_text("main2")
    repo_factory.run(["add", "main2.txt"], cwd=path)
    repo_factory.run(["commit", "-m", "main2"], cwd=path)
    
    repo_factory.run(["checkout", "topic"], cwd=path)
    res = repo_factory.run(["rebase", "main"], cwd=path)
    assert res.returncode == 0
