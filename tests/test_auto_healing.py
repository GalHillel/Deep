"""
tests.test_auto_healing
~~~~~~~~~~~~~~~~~~~~~~
Tests for Phase 57: AI-Driven Auto-Self-Healing (P2P recovery).
"""

import pytest
import time
import zlib
from pathlib import Path
from deep.core.repository import init_repo, DEEP_GIT_DIR
from deep.storage.objects import Blob, read_object_safe


@pytest.fixture
def healing_env(tmp_path):
    r1 = tmp_path / "repo1"; r2 = tmp_path / "repo2"
    r1.mkdir(); r2.mkdir()
    init_repo(r1); init_repo(r2)
    return r1, r2


def test_p2p_auto_heal(healing_env):
    r1, r2 = healing_env
    
    # 1. Create a valid object in both repos
    data = b"stable content"
    b1 = Blob(data=data)
    sha = b1.write(r1 / DEEP_GIT_DIR / "objects")
    b2 = Blob(data=data)
    b2.write(r2 / DEEP_GIT_DIR / "objects")
    
    # 2. Corrupt the object in r2
    obj_path = r2 / DEEP_GIT_DIR / "objects" / sha[:2] / sha[2:]
    obj_path.write_bytes(zlib.compress(b"CORRUPT DATA"))
    
    # 3. Setup P2P discovery so r2 knows about r1
    from deep.network.p2p import P2PEngine, PeerNode
    e2 = P2PEngine(r2 / DEEP_GIT_DIR)
    # Manually seed r1 as a peer of r2
    e2.peers["node_1"] = PeerNode(
        node_id="node_1",
        host="127.0.0.1",
        port=0,
        last_seen=time.time(),
        branches={},
        repo_name="repo1"
    )
    
    # We need a way to make read_object_safe use our engine.
    # For the test, we can monkeypatch P2PEngine to return our instance.
    import deep.storage.objects
    original_p2p = deep.storage.objects._attempt_p2p_heal
    
    def mock_heal(dg_dir, target_sha):
        return e2.request_tunnel_data("node_1", target_sha)
        
    deep.storage.objects._attempt_p2p_heal = mock_heal
    
    try:
        # 4. Attempt to read the corrupt object in r2
        # It should trigger healing and succeed
        obj = read_object_safe(r2 / DEEP_GIT_DIR / "objects", sha)
        assert obj.data == data
        
        # 5. Verify it's actually fixed on disk
        new_data = zlib.decompress(obj_path.read_bytes())
        assert b"stable content" in new_data
        
    finally:
        deep.storage.objects._attempt_p2p_heal = original_p2p
