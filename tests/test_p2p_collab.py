"""
tests.test_p2p_collab
~~~~~~~~~~~~~~~~~~~~~
Tests for Phase 54: Real-Time Multi-User Collaboration & P2P Tunnels.
"""

import pytest
import time
import socket
from pathlib import Path
from deep.core.repository import init_repo
from deep.network.p2p import P2PEngine


@pytest.fixture
def p2p_repos(tmp_path):
    repo1 = tmp_path / "repo1"
    repo2 = tmp_path / "repo2"
    repo1.mkdir(); repo2.mkdir()
    init_repo(repo1); init_repo(repo2)
    return repo1, repo2


def test_p2p_presence_propagation(p2p_repos):
    r1, r2 = p2p_repos
    e1 = P2PEngine(r1 / ".deep")
    e2 = P2PEngine(r2 / ".deep")
    
    e1.start()
    e2.start()
    
    try:
        # Update presence on e1
        e1.update_presence("main.py", 42)
        
        # Wait for discovery (beaconing)
        timeout = 10
        found = False
        start = time.time()
        while time.time() - start < timeout:
            peers = e2.get_peers()
            for p in peers:
                if p.node_id == e1.node_id:
                    if e1.node_id in p.presence:
                        pres = p.presence[e1.node_id]
                        if pres.get("file") == "main.py":
                            found = True
                            break
            if found: break
            time.sleep(0.5)
            
        assert found, f"Presence from {e1.node_id} not found in {e2.node_id} peers"
    finally:
        e1.stop()
        e2.stop()


def test_p2p_tunnel_simulation(p2p_repos):
    r1, r2 = p2p_repos
    # repo1 has an object
    (r1 / "data.txt").write_text("secret data")
    from deep.commands.add_cmd import run as run_add
    from deep.commands.commit_cmd import run as run_commit
    
    import os
    old_cwd = os.getcwd()
    os.chdir(r1)
    class Args: pass
    add_args = Args(); add_args.files = ["data.txt"]
    run_add(add_args)
    commit_args = Args(); commit_args.message = "add data"; commit_args.sign = False
    run_commit(commit_args)
    
    from deep.core.refs import resolve_head
    head_sha = resolve_head(r1 / ".deep")
    os.chdir(old_cwd)
    
    e1 = P2PEngine(r1 / ".deep")
    e2 = P2PEngine(r2 / ".deep")
    
    # Manually add e1 to e2's peers to avoid waiting for beacon
    from deep.network.p2p import PeerNode
    e2.peers[e1.node_id] = PeerNode(
        node_id=e1.node_id,
        host="127.0.0.1",
        port=0,
        last_seen=time.time(),
        branches={},
        repo_name="repo1"
    )
    
    # Request data via tunnel from e2 to e1
    data = e2.request_tunnel_data(e1.node_id, head_sha)
    assert data is not None
    assert b"author" in data # It's a commit object
