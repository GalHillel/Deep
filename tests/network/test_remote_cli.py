"""
tests.test_remote_cli
~~~~~~~~~~~~~~~~~~~~~
End-to-end tests for deep clone, push, and fetch.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

from deep.core.repository import DEEP_DIR
from deep.core.refs import resolve_head


def get_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]


@pytest.fixture
def env():
    e = os.environ.copy()
    e["PYTHONPATH"] = str(Path.cwd())
    e["PYTHONUNBUFFERED"] = "1"
    return e


def test_distributed_workflow(tmp_path: Path, env: dict[str, str]):
    # 1. Setup Server Repo
    server_root = tmp_path / "server"
    server_root.mkdir()
    subprocess.run([sys.executable, "-m", "deep.cli.main", "init"], cwd=server_root, env=env, check=True)
    
    # Add a commit to server
    (server_root / "README.md").write_text("Server Repo")
    subprocess.run([sys.executable, "-m", "deep.cli.main", "add", "README.md"], cwd=server_root, env=env, check=True)
    subprocess.run([sys.executable, "-m", "deep.cli.main", "commit", "-m", "server init"], cwd=server_root, env=env, check=True)
    server_head = resolve_head(server_root / DEEP_DIR)

    # 1.5 Setup Authorization (new security policy requires explicit write access)
    from deep.core.user import UserManager
    from deep.core.access import AccessManager
    um = UserManager(server_root / DEEP_DIR)
    um.add_user("anonymous", "test-key", "anon@example.com")
    am = AccessManager(server_root / DEEP_DIR)
    am.set_permission("anonymous", "contributor")
    
    # 2. Start Server Daemon
    port = get_free_port()
    # We redirect to files to avoid blocking on PIPE buffers on Windows
    log_out = open(tmp_path / "daemon_stdout.log", "w")
    log_err = open(tmp_path / "daemon_stderr.log", "w")
    server_proc = subprocess.Popen(
        [sys.executable, "-m", "deep.cli.main", "daemon", "--port", str(port)],
        cwd=server_root,
        env=env,
        stdout=log_out,
        stderr=log_err
    )
    time.sleep(1)
    
    try:
        # 3. Clone to Client 1
        client1_root = tmp_path / "client1"
        # Since clone creates the directory, we just pass the path
        subprocess.run([sys.executable, "-m", "deep.cli.main", "clone", f"127.0.0.1:{port}", str(client1_root)], env=env, check=True)
        
        # Verify client1 init worked
        assert (client1_root / DEEP_DIR).exists()
        
        # 4. Client 1 makes changes and Pushes
        # We need to manually set up a commit in client1 for now because clone is a bit of a stub
        # Let's just create a new commit in client1
        (client1_root / "feature.txt").write_text("new feature")
        subprocess.run([sys.executable, "-m", "deep.cli.main", "add", "feature.txt"], cwd=client1_root, env=env, check=True)
        subprocess.run([sys.executable, "-m", "deep.cli.main", "commit", "-m", "feat commit"], cwd=client1_root, env=env, check=True)
        client1_head = resolve_head(client1_root / DEEP_DIR)
        
        # Push to server
        subprocess.run([sys.executable, "-m", "deep.cli.main", "push", f"127.0.0.1:{port}", "main"], cwd=client1_root, env=env, check=True)
        
        # 5. Verify Server updated
        server_head_after = resolve_head(server_root / DEEP_DIR)
        assert server_head_after == client1_head
        
        # 6. Client 2 Clones (or Fetches)
        client2_root = tmp_path / "client2"
        subprocess.run([sys.executable, "-m", "deep.cli.main", "clone", f"127.0.0.1:{port}", str(client2_root)], env=env, check=True)
        
        # Fetch the new SHA from server
        subprocess.run([sys.executable, "-m", "deep.cli.main", "fetch", f"127.0.0.1:{port}", client1_head], cwd=client2_root, env=env, check=True)
        
        # Verify client2 has the object
        from deep.storage.objects import read_object
        obj = read_object(client2_root / DEEP_DIR / "objects", client1_head)
        assert obj.sha == client1_head
        
    finally:
        server_proc.terminate()
        server_proc.wait()
        log_out.close()
        log_err.close()
        
        # If the test failed, the logs might be useful
        try:
            print("DAEMON OUT:", (tmp_path / "daemon_stdout.log").read_text())
            print("DAEMON ERR:", (tmp_path / "daemon_stderr.log").read_text())
        except:
            pass
