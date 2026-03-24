import time
import pytest

def test_p2p_mesh_sync(repo_factory):
    """Sync across 3 isolated nodes."""
    node_a = repo_factory.create("node_a")
    (node_a / "core.txt").write_text("v1")
    repo_factory.run(["add", "core.txt"], cwd=node_a)
    repo_factory.run(["commit", "-m", "v1"], cwd=node_a)
    
    node_b = repo_factory.create("node_b")
    node_c = repo_factory.create("node_c")
    
    # Sync A -> B
    res = repo_factory.run(["sync", "--peer", str(node_a)], cwd=node_b)
    assert res.returncode == 0
    assert (node_b / "core.txt").exists()
    
    # Sync B -> C
    res = repo_factory.run(["sync", "--peer", str(node_b)], cwd=node_c)
    assert res.returncode == 0
    assert (node_c / "core.txt").exists()

def test_p2p_interrupted_sync(repo_factory):
    node_a = repo_factory.create("node_a_fault")
    (node_a / "large.bin").write_text("data" * 1000)
    repo_factory.run(["add", "large.bin"], cwd=node_a)
    repo_factory.run(["commit", "-m", "large"], cwd=node_a)
    
    node_b = repo_factory.create("node_b_fault")
    proc = repo_factory.spawn(["sync", "--peer", str(node_a)], cwd=node_b)
    time.sleep(0.05)
    proc.kill()
    
    # Integrity check
    res = repo_factory.run(["fsck"], cwd=node_b)
    assert res.returncode == 0

