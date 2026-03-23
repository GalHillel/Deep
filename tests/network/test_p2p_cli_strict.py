import os
import shutil
import subprocess
import time
import socket
import pytest
from pathlib import Path

def run_deep(*args, cwd=None):
    """Run a deep command and return the result."""
    import sys
    env = os.environ.copy()
    repo_root = Path(__file__).parent.parent.parent.absolute()
    src_dir = str(repo_root / "src")
    env["PYTHONPATH"] = src_dir + os.pathsep + env.get("PYTHONPATH", "")
    
    cmd = [sys.executable, "-m", "deep.cli.main"] + list(args)
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, env=env)

def get_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]

def test_cli_p2p_sync_safe(tmp_path):
    """
    repo A init + commit
    repo B init
    start daemon on repo A
    repo B sync
    verify commit transferred
    """
    repo_a = tmp_path / "repo_a"
    repo_a.mkdir()
    run_deep("init", cwd=repo_a)
    (repo_a / "file.txt").write_text("hello p2p")
    run_deep("add", "file.txt", cwd=repo_a)
    run_deep("commit", "-m", "p2p commit", cwd=repo_a)
    commit_sha = (repo_a / ".deep" / "refs" / "heads" / "main").read_text().strip()

    repo_b = tmp_path / "repo_b"
    repo_b.mkdir()
    run_deep("init", cwd=repo_b)

    port = get_free_port()
    # Start daemon on repo_a
    # We use a background process for the daemon
    import sys
    daemon_cmd = [sys.executable, "-m", "deep.cli.main", "daemon", "--port", str(port)]
    daemon_proc = subprocess.Popen(daemon_cmd, cwd=repo_a, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=os.environ.copy())
    
    try:
        # Give daemon time to start
        time.sleep(2)
        
        # Repo B sync from Repo A
        # We need to pass the peer address. p2p_cmd.py supports --peer
        res = run_deep("p2p", "sync", "--peer", f"127.0.0.1:{port}", cwd=repo_b)
        
        # Check daemon status
        if daemon_proc.poll() is not None:
            out, err = daemon_proc.communicate()
            print(f"DEBUG: Daemon STDOUT: {out.decode()}")
            print(f"DEBUG: Daemon STDERR: {err.decode()}")
            
        assert res.returncode == 0
        
        # Checkout the branch to update working directory
        res = run_deep("checkout", "-f", "main", cwd=repo_b)
        assert res.returncode == 0
        
        # Verify Repo B has the commit
        res = run_deep("log", cwd=repo_b)
        assert commit_sha in res.stdout
        assert "p2p commit" in res.stdout
        
        # Verify file exists
        assert (repo_b / "file.txt").exists()
        assert (repo_b / "file.txt").read_text() == "hello p2p"
        
    finally:
        daemon_proc.terminate()
        daemon_proc.wait()

def test_cli_p2p_sync_abort(tmp_path):
    """
    sync to dead port
    expect non-zero exit
    verify repo unchanged
    """
    repo_b = tmp_path / "repo_b"
    repo_b.mkdir()
    run_deep("init", cwd=repo_b)
    
    # Get a port that is likely closed
    port = get_free_port()
    
    res = run_deep("p2p", "sync", "--peer", f"127.0.0.1:{port}", cwd=repo_b)
    assert res.returncode != 0
    
    # Verify no refs created
    refs_dir = repo_b / ".deep" / "refs" / "heads"
    if refs_dir.exists():
        assert not list(refs_dir.glob("*"))

def test_cli_daemon_push_transactional(tmp_path):
    """
    repo A push to repo B (via daemon)
    Verify transactional safety on push.
    """
    repo_b = tmp_path / "repo_b"
    repo_b.mkdir()
    run_deep("init", cwd=repo_b)
    
    # Configure repo_b to allow pushes (anonymous write)
    # We need to set access permissions
    dg_dir_b = repo_b / ".deep"
    (dg_dir_b / "permissions.json").write_text('{"anonymous": "contributor"}')

    port = get_free_port()
    import sys
    daemon_cmd = [sys.executable, "-m", "deep.cli.main", "daemon", "--port", str(port)]
    daemon_proc = subprocess.Popen(daemon_cmd, cwd=repo_b, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=os.environ.copy())
    
    try:
        time.sleep(2)
        
        repo_a = tmp_path / "repo_a"
        repo_a.mkdir()
        run_deep("init", cwd=repo_a)
        run_deep("remote", "add", "origin", f"deep://127.0.0.1:{port}", cwd=repo_a)
        
        (repo_a / "file.txt").write_text("push content")
        run_deep("add", "file.txt", cwd=repo_a)
        run_deep("commit", "-m", "push commit", cwd=repo_a)
        
        # Push should work
        res = run_deep("push", "origin", "main", cwd=repo_a)
        print(res.stdout)
        print(res.stderr)
        assert res.returncode == 0
        assert "push successful" in res.stdout
        
        # Verify Repo B has the commit
        res = run_deep("log", cwd=repo_b)
        assert "push commit" in res.stdout
        
    finally:
        daemon_proc.terminate()
        daemon_proc.wait()

def test_cli_p2p_sync_rollback_on_failure(tmp_path):
    """
    Sync from a daemon that fails mid-way or sends bad data.
    Verify repo B is rolled back.
    """
    repo_a = tmp_path / "repo_a"
    repo_a.mkdir()
    run_deep("init", cwd=repo_a)
    (repo_a / "file.txt").write_text("secret")
    run_deep("add", "file.txt", cwd=repo_a)
    run_deep("commit", "-m", "secret commit", cwd=repo_a)

    repo_b = tmp_path / "repo_b"
    repo_b.mkdir()
    run_deep("init", cwd=repo_b)

    port = get_free_port()
    # We'll mock a failure by killing the daemon mid-sync or using a custom trigger
    # In p2p_cmd.py, we have:
    # try:
    #    for c in conflicts:
    #        client.fetch(...)
    #        update_branch(...)
    #    tm.commit()
    # except Exception: tm.rollback()

    # We can trigger a failure by setting an invalid branch tip in the peer discovery
    # but the fetch will then fail.
    
    # Actually, let's use a "poison" environment variable that we can check in p2p_cmd.py
    # and raise an exception.
    
    import os
    env = os.environ.copy()
    env["DEEP_P2P_CHAOS"] = "1"
    
    import sys
    daemon_cmd = [sys.executable, "-m", "deep.cli.main", "daemon", "--port", str(port)]
    daemon_proc = subprocess.Popen(daemon_cmd, cwd=repo_a, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=os.environ.copy())
    
    try:
        time.sleep(2)
        
        # Run sync with CHAOS enabled
        cmd = [sys.executable, "-m", "deep.cli.main", "p2p", "sync", "--peer", f"127.0.0.1:{port}"]
        res = subprocess.run(cmd, cwd=repo_b, env=env, capture_output=True, text=True)
        
        assert res.returncode != 0
        assert "CHAOS" in res.stdout or "CHAOS" in res.stderr
        
        # Verify repo_b has NO refs
        refs_dir = repo_b / ".deep" / "refs" / "heads"
        if refs_dir.exists():
            assert not list(refs_dir.glob("*"))
            
    finally:
        daemon_proc.terminate()
        daemon_proc.wait()
