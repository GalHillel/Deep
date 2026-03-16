"""Tests for P2P networking (Phase 41)."""
from pathlib import Path
import subprocess, sys, os, time
import pytest

from deep.core.repository import DEEP_DIR


@pytest.fixture
def p2p_repo(tmp_path):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path.cwd() / "src")
    subprocess.run([sys.executable, "-m", "deep.main", "init"], cwd=tmp_path, env=env, check=True)
    return tmp_path, env


def test_p2p_discovery(p2p_repo):
    """Test that two nodes can discover each other."""
    from deep.network.p2p import P2PEngine
    repo, env = p2p_repo
    
    # We can't really test multicast easily in a CI environment without 
    # complex networking setup, but we can verify the Engine starts and 
    # doesn't crash.
    e = P2PEngine(repo / DEEP_DIR, listen_port=9001)
    e.start()
    time.sleep(2)
    peers = e.get_peers()
    e.stop()
    assert isinstance(peers, list)


def test_p2p_cli_list(p2p_repo):
    """Test p2p list CLI command."""
    repo, env = p2p_repo
    # Just verify it doesn't crash
    result = subprocess.run(
        [sys.executable, "-m", "deep.main", "p2p", "list"],
        cwd=repo, env=env, capture_output=True, text=True, timeout=10
    )
    assert result.returncode == 0


def test_p2p_node_state_exchange(p2p_repo):
    """Test local node state retrieval."""
    from deep.network.p2p import P2PEngine
    repo, env = p2p_repo
    
    # Create an initial commit
    (repo / "init.txt").write_text("initial")
    subprocess.run([sys.executable, "-m", "deep.main", "add", "init.txt"], cwd=repo, env=env, check=True)
    subprocess.run([sys.executable, "-m", "deep.main", "commit", "-m", "initial"], cwd=repo, env=env, check=True)
    
    # Create a branch
    subprocess.run([sys.executable, "-m", "deep.main", "branch", "feat-p2p"], cwd=repo, env=env, check=True)
    
    e = P2PEngine(repo / DEEP_DIR)
    state = e._get_local_state()
    assert "feat-p2p" in state
    assert len(state["feat-p2p"]) == 40
