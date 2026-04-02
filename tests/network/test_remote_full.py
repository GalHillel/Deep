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
import pytest
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
        
def run_deep(*args, cwd=None, env=None):
    import sys
    cmd = [sys.executable, "-m", "deep.cli.main"] + list(args)
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, env=env or os.environ.copy())
        
def run_daemon(repo_path, port):
    os.chdir(repo_path)
    # We use subprocess to avoid issues with asyncio and multiprocessing in tests
    subprocess.run([sys.executable, "-m", "deep.cli.main", "daemon", "--port", str(port)], timeout=30)

@pytest.fixture()
def remote_repo(tmp_path: Path) -> Path:
    remote_dir = tmp_path / "remote_repo"
    remote_dir.mkdir()
    os.chdir(remote_dir)
    main(["init"])
    (remote_dir / "file.txt").write_text("remote content")
    main(["add", "file.txt"])
    main(["commit", "-m", "Initial remote commit"])

    # Setup Authorization for tests
    from deep.core.user import UserManager
    from deep.core.access import AccessManager
    from deep.core.repository import DEEP_DIR
    dg_dir = remote_dir / DEEP_DIR
    um = UserManager(dg_dir)
    um.add_user("anonymous", "test-key", "anon@example.com")
    am = AccessManager(dg_dir)
    am.set_permission("anonymous", "contributor")

    return remote_dir

def test_full_remote_workflow(remote_repo: Path, tmp_path: Path) -> None:
    # 1. Start Daemon in background
    port = get_free_port()

    # Using a background process for daemon
    # Note: deep daemon is an infinite loop, so we'll need to kill it
    p = subprocess.Popen([sys.executable, "-m", "deep.cli.main", "daemon", "--port", str(port)], cwd=remote_repo)
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
        main(["remote", "add", "upstream", f"localhost:{port}"])
        
        # 4. Verify remote list
        # We'll capture output or check config
        config = Config(client_dir)
        assert config.get("remote.upstream.url") == f"localhost:{port}"

        # 5. Push new commit
        (client_dir / "new.txt").write_text("client content")
        run_deep("add", "new.txt", cwd=client_dir)
        run_deep("commit", "-m", "Client commit", cwd=client_dir)
        
        main(["push", "upstream", "main"])
        
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
        run_deep("add", "update.txt", cwd=client_dir)
        run_deep("commit", "-m", "Update from client", cwd=client_dir)
        main(["push", "upstream", "main"])
        
        os.chdir(other_client)
        main(["pull", "origin", "main"]) # origin is fine here because it comes from clone
        assert (other_client / "update.txt").exists()
        assert (other_client / "update.txt").read_text() == "update"
        
        print("Full remote workflow PASSED")

    finally:
        p.terminate()
        p.wait()
