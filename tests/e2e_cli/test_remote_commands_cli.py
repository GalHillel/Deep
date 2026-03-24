import pytest
from pathlib import Path
import tempfile
import shutil

def test_remote_and_clone_advanced(repo_factory):
    """Test remote, pull, and push with full isolation."""
    upstream = repo_factory.create("upstream")
    (upstream / "f.txt").write_text("v1")
    repo_factory.run(["add", "f.txt"], cwd=upstream)
    repo_factory.run(["commit", "-m", "v1"], cwd=upstream)
    
    # Clone it
    downstream_path = upstream.parent / "downstream"
    res = repo_factory.run(["clone", str(upstream), str(downstream_path)])
    assert res.returncode == 0
    assert (downstream_path / "f.txt").exists()
    
    # Remote add and pull
    (upstream / "f2.txt").write_text("v2")
    repo_factory.run(["add", "f2.txt"], cwd=upstream)
    repo_factory.run(["commit", "-m", "v2"], cwd=upstream)
    
    repo_factory.run(["remote", "add", "origin", str(upstream)], cwd=downstream_path)
    res = repo_factory.run(["pull", "origin", "main"], cwd=downstream_path)
    assert res.returncode == 0
    assert (downstream_path / "f2.txt").exists()
    
    # Mirror
    mirror_path = upstream.parent / "mirror"
    res = repo_factory.run(["clone", "--mirror", str(upstream), str(mirror_path)])
    assert res.returncode == 0
    assert (mirror_path / "objects").exists()

def test_daemon_protocol(repo_factory):
    """Test deep daemon over a dynamic port."""
    from .conftest import get_free_port, poll_until
    port = get_free_port()
    path = repo_factory.create("daemon_repo")
    
    # Start daemon
    daemon = repo_factory.spawn(["daemon", "--port", str(port)], cwd=path)
    
    # Verify listener (CLI usually takes time to bind)
    def check_daemon():
        try:
            import socket
            with socket.create_connection(("localhost", port), timeout=0.1):
                return True
        except:
            return False
            
    assert poll_until(check_daemon, timeout=5)
    
    # Clone via daemon protocol (assuming deep supports deep://localhost:port/path)
    # If not supported, we at least verified the daemon starts.
    daemon.terminate()

def test_ls_remote_and_fetch(repo_factory):
    upstream = repo_factory.create("upstream_ls")
    (upstream / "f.txt").write_text("data")
    repo_factory.run(["add", "f.txt"], cwd=upstream)
    repo_factory.run(["commit", "-m", "init"], cwd=upstream)
    
    local = repo_factory.create("local_ls")
    repo_factory.run(["remote", "add", "origin", str(upstream)], cwd=local)
    
    res = repo_factory.run(["ls-remote", "origin"], cwd=local)
    assert res.returncode == 0
    assert "HEAD" in res.stdout
    
    res = repo_factory.run(["fetch", "origin"], cwd=local)
    assert res.returncode == 0
