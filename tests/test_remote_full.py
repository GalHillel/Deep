"""
tests.test_remote_full
~~~~~~~~~~~~~~~~~~~~~~
End-to-end test for Phase 5 remote support.
"""

from __future__ import annotations

import os
import time
import sys
import subprocess
import socket
from pathlib import Path
from multiprocessing import Process

import pytest

from deep.cli.main import main
from deep.core.repository import DEEP_DIR
from deep.core.refs import resolve_head
from deep.core.config import Config

def get_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]
        
def run_daemon(repo_path, port):
    os.chdir(repo_path)
    # We use subprocess to avoid issues with asyncio and multiprocessing in tests
    subprocess.run([sys.executable, "-m", "deep.main", "daemon", "--port", str(port)], timeout=30)

@pytest.fixture()
def remote_repo(tmp_path: Path) -> Path:
    remote_dir = tmp_path / "remote_repo"
    remote_dir.mkdir()
    os.chdir(remote_dir)
    main(["init"])
    (remote_dir / "file.txt").write_text("remote content")
    main(["add", "file.txt"])
    main(["commit", "-m", "Initial remote commit"])
    return remote_dir

def test_full_remote_workflow(remote_repo: Path, tmp_path: Path) -> None:
    # 1. Start Daemon in background
    port = get_free_port()

    # Using a background process for daemon
    # Note: deep daemon is an infinite loop, so we'll need to kill it
    p = subprocess.Popen([sys.executable, "-m", "deep.main", "daemon", "--port", str(port)], cwd=remote_repo)
    time.sleep(2) # Wait for startup

    try:
        # 2. Clone from daemon
        client_dir = tmp_path / "client_repo"
        os.chdir(tmp_path)
        main(["clone", f"localhost:{port}", "client_repo"])
        
        assert (client_dir / "file.txt").exists()
        assert (client_dir / "file.txt").read_text() == "remote content"

        # 3. Add remote
        os.chdir(client_dir)
        main(["remote", "add", "origin", f"localhost:{port}"])
        
        # 4. Verify remote list
        # We'll capture output or check config
        config = Config(client_dir)
        assert config.get("remote.origin.url") == f"localhost:{port}"

        # 5. Push new commit
        (client_dir / "new.txt").write_text("client content")
        main(["add", "new.txt"])
        main(["commit", "-m", "Client commit"])
        
        main(["push", "origin", "main"])
        
        # 6. Verify remote repo has the commit (via pull in another clone)
        other_client = tmp_path / "other_client"
        os.chdir(tmp_path)
        main(["clone", f"localhost:{port}", "other_client"])
        assert (other_client / "new.txt").exists()
        
        # 7. Test Pull
        # Make another commit on remote_repo? 
        # Since daemon is running on remote_repo, we can just edit files and commit there
        # But wait, daemon is running in a subprocess. 
        # Let's just use push from client_repo and pull from other_client.
        
        os.chdir(client_dir)
        (client_dir / "update.txt").write_text("update")
        main(["add", "update.txt"])
        main(["commit", "-m", "Update from client"])
        main(["push", "origin", "main"])
        
        os.chdir(other_client)
        main(["pull", "origin", "main"])
        assert (other_client / "update.txt").exists()
        assert (other_client / "update.txt").read_text() == "update"
        
        print("Full remote workflow PASSED")

    finally:
        p.terminate()
        p.wait()
