"""
tests.test_smart_clone
~~~~~~~~~~~~~~~~~~~~~~~
Tests for shallow clone (--depth) and partial clone (--filter).
"""

from __future__ import annotations

import os
import threading
import time
import socket
from pathlib import Path

import pytest

from deep.core.repository import DEEP_DIR
from deep.storage.objects import read_object, Blob, Commit
from deep.cli.main import main
from deep.network.daemon import DeepDaemon

@pytest.fixture()
def remote_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "remote"
    repo.mkdir()
    os.chdir(repo)
    main(["init"])
    
    # Create 3 commits
    for i in range(3):
        f = repo / f"file{i}.txt"
        f.write_text(f"content {i}")
        main(["add", f"file{i}.txt"])
        main(["commit", "-m", f"commit {i}"])
        time.sleep(0.1) # Ensure different timestamps if needed
        
    return repo

def get_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]

@pytest.fixture()
def daemon(remote_repo: Path):
    port = get_free_port()
    d = DeepDaemon(remote_repo, host="127.0.0.1", port=port)
    
    import asyncio
    loop = asyncio.new_event_loop()
    
    def run_daemon():
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(d.start())
        except (asyncio.CancelledError, RuntimeError):
            pass
        
    t = threading.Thread(target=run_daemon, daemon=True)
    t.start()
    
    time.sleep(1) # Wait for start
    yield (d, port)
    
    # Shutdown
    loop.call_soon_threadsafe(loop.stop)
    t.join(timeout=5)
    if loop.is_running():
        loop.stop()
    if not loop.is_closed():
        loop.close()

@pytest.mark.skip(reason="Experimental P2P/Server features currently disabled in main.py")
def test_shallow_clone(remote_repo: Path, daemon: tuple[DeepDaemon, int], tmp_path: Path):
    d, port = daemon
    clone_dir = tmp_path / "shallow_clone"
    os.chdir(tmp_path)
    
    # Depth 1 clone
    main(["clone", f"127.0.0.1:{port}", str(clone_dir), "--depth", "1"])
    
    dg_dir = clone_dir / DEEP_DIR
    obj_dir = dg_dir / "objects"
    
    # Let's check objects in clone
    shas = []
    for root, dirs, files in os.walk(obj_dir):
        if "pack" in root: continue
        for f in files:
            if len(Path(root).name) == 2:
                shas.append(Path(root).name + f)
    
    # Find the latest commit SHA in remote
    from deep.core.refs import resolve_head
    latest_sha = resolve_head(remote_repo / DEEP_DIR)
    
    # The clone should have the latest commit
    assert latest_sha in shas
    
    # Get parent of latest commit
    latest_obj = read_object(remote_repo / DEEP_DIR / "objects", latest_sha)
    assert isinstance(latest_obj, Commit)
    parent_sha = latest_obj.parent_shas[0] if latest_obj.parent_shas else None
    
    if parent_sha:
        # Shallow clone of depth 1 should NOT have the parent commit object
        assert parent_sha not in shas

@pytest.mark.skip(reason="Experimental P2P/Server features currently disabled in main.py")
def test_partial_clone_blobless(remote_repo: Path, daemon: tuple[DeepDaemon, int], tmp_path: Path):
    d, port = daemon
    clone_dir = tmp_path / "partial_clone"
    os.chdir(tmp_path)
    
    # Blobless clone
    main(["clone", f"127.0.0.1:{port}", str(clone_dir), "--filter", "blob:none"])
    
    dg_dir = clone_dir / DEEP_DIR
    obj_dir = dg_dir / "objects"
    
    shas = []
    for root, dirs, files in os.walk(obj_dir):
        if "pack" in root: continue
        for f in files:
            if len(Path(root).name) == 2:
                shas.append(Path(root).name + f)
    
    # Verify no blobs in the object store
    blobs_found = 0
    for sha in shas:
        try:
            # We use the raw file check to avoid instantiating and seeing if it's a blob
            # but read_object is safer to check type
            obj = read_object(obj_dir, sha)
            if isinstance(obj, Blob):
                blobs_found += 1
        except:
            pass
            
    assert blobs_found == 0
    
    # Should still have the commit
    from deep.core.refs import resolve_head
    latest_sha = resolve_head(remote_repo / DEEP_DIR)
    assert latest_sha in shas
