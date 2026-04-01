import subprocess
import pytest
from pathlib import Path
import time
import socket

def run_deep_bg(repo_dir, args):
    """Run a deep command in the background."""
    return subprocess.Popen(
        ["deep"] + args,
        cwd=repo_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

def run_deep(repo_dir, args):
    """Run a deep command and return the result."""
    result = subprocess.run(
        ["deep"] + args,
        cwd=repo_dir,
        capture_output=True,
        text=True
    )
    return result

@pytest.fixture
def repo(tmp_path):
    repo_dir = tmp_path / "test_repo"
    repo_dir.mkdir()
    run_deep(repo_dir, ["init"])
    return repo_dir

def test_daemon_help(repo):
    """Test deep daemon -h matches expected usage."""
    res = run_deep(repo, ["daemon", "-h"])
    assert res.returncode == 0
    assert "usage: deep daemon" in res.stdout
    assert "--port PORT" in res.stdout

def test_daemon_start_default_port(repo):
    """Test deep daemon starts on the default port (9090)."""
    proc = run_deep_bg(repo, ["daemon"])
    # Give it a moment to start
    time.sleep(2)
    
    try:
        # Check if port is listening
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1)
        res = s.connect_ex(('127.0.0.1', 9090))
        s.close()
        assert res == 0
    finally:
        proc.terminate()
        proc.wait()

def test_daemon_custom_port(repo):
    """Test deep daemon starts on a custom port."""
    port = 9876
    proc = run_deep_bg(repo, ["daemon", "--port", str(port)])
    time.sleep(2)
    
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1)
        res = s.connect_ex(('127.0.0.1', port))
        s.close()
        assert res == 0
    finally:
        proc.terminate()
        proc.wait()

def test_daemon_no_repo(tmp_path):
    """Test deep daemon fails outside of a repository."""
    res = run_deep(tmp_path, ["daemon"])
    assert res.returncode != 0
    assert "Not a Deep repository" in res.stderr
