import pytest
import shutil
import tempfile
from pathlib import Path

def test_remote_tracking_and_flow(repo_factory):
    """Verify tracking branches and push/pull flow."""
    upstream = repo_factory.create("upstream")
    (upstream / "README.md").write_text("v1")
    repo_factory.run(["add", "README.md"], cwd=upstream)
    repo_factory.run(["commit", "-m", "v1"], cwd=upstream)
    
    downstream = Path(tempfile.mkdtemp())
    repo_factory.run(["clone", str(upstream), str(downstream)])
    
    # Check tracking
    res = repo_factory.run(["branch", "-vv"], cwd=downstream)
    assert "origin/main" in res.stdout
    
    # Push new branch
    repo_factory.run(["checkout", "-b", "feature"], cwd=downstream)
    (downstream / "feat.txt").write_text("data")
    repo_factory.run(["add", "feat.txt"], cwd=downstream)
    repo_factory.run(["commit", "-m", "feat"], cwd=downstream)
    
    res = repo_factory.run(["push", "-u", "origin", "feature"], cwd=downstream)
    assert res.returncode == 0
    
    # Verify upstream has it
    res = repo_factory.run(["branch"], cwd=upstream)
    assert "feature" in res.stdout
    shutil.rmtree(downstream)

def test_force_push_and_ls_remote(repo_factory):
    """Test push --force and ls-remote."""
    upstream = repo_factory.create("upstream_force")
    (upstream / "f.txt").write_text("v1")
    repo_factory.run(["add", "f.txt"], cwd=upstream)
    repo_factory.run(["commit", "-m", "v1"], cwd=upstream)
    
    downstream = Path(tempfile.mkdtemp())
    repo_factory.run(["clone", str(upstream), str(downstream)])
    
    # ls-remote
    res = repo_factory.run(["ls-remote", "origin"], cwd=downstream)
    assert "HEAD" in res.stdout
    
    # Rewriting history
    repo_factory.run(["commit", "--amend", "-m", "v1-rewritten"], cwd=downstream)
    
    # Normal push should fail
    res = repo_factory.run(["push"], cwd=downstream)
    assert res.returncode != 0
    
    # Force push should succeed
    res = repo_factory.run(["push", "--force"], cwd=downstream)
    assert res.returncode == 0
    
    # Verify upstream was rewritten
    res = repo_factory.run(["log", "-n", "1"], cwd=upstream)
    assert "v1-rewritten" in res.stdout
    shutil.rmtree(downstream)

def test_push_pull_conflicts(repo_factory):
    """Simulate push/pull conflicts and resolution."""
    upstream = repo_factory.create("upstream_conflict")
    (upstream / "shared.txt").write_text("initial")
    repo_factory.run(["add", "shared.txt"], cwd=upstream)
    repo_factory.run(["commit", "-m", "initial"], cwd=upstream)
    
    # Clone two peers
    p1 = Path(tempfile.mkdtemp())
    p2 = Path(tempfile.mkdtemp())
    repo_factory.run(["clone", str(upstream), str(p1)])
    repo_factory.run(["clone", str(upstream), str(p2)])
    
    # P1 pushes
    (p1 / "shared.txt").write_text("p1 edit")
    repo_factory.run(["add", "shared.txt"], cwd=p1)
    repo_factory.run(["commit", "-m", "p1"], cwd=p1)
    repo_factory.run(["push"], cwd=p1)
    
    # P2 edits same file
    (p2 / "shared.txt").write_text("p2 edit")
    repo_factory.run(["add", "shared.txt"], cwd=p2)
    repo_factory.run(["commit", "-m", "p2"], cwd=p2)
    
    # P2 push should fail
    res = repo_factory.run(["push"], cwd=p2)
    assert res.returncode != 0
    
    # P2 pull should result in conflict
    res = repo_factory.run(["pull"], cwd=p2)
    assert "CONFLICT" in res.stdout or res.returncode != 0
    
    # Resolve
    (p2 / "shared.txt").write_text("p1 and p2 merged")
    repo_factory.run(["add", "shared.txt"], cwd=p2)
    repo_factory.run(["commit", "-m", "resolved"], cwd=p2)
    
    # P2 push should now succeed
    res = repo_factory.run(["push"], cwd=p2)
    assert res.returncode == 0
    
    shutil.rmtree(p1)
    shutil.rmtree(p2)
