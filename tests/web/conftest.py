import pytest
import multiprocessing
import time
import socket
from pathlib import Path
from deep.web.dashboard import start_dashboard
from deep.core.repository import init_repo
from deep.cli.main import main

def get_free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('', 0))
    port = s.getsockname()[1]
    s.close()
    return port

@pytest.fixture(scope="session")
def dashboard_server(tmp_path_factory):
    """
    Starts a dashboard server with a sample repository containing 3 commits.
    Yields (port, repo_path).
    """
    tmp_dir = tmp_path_factory.mktemp("dashboard_session")
    repo = tmp_dir / "repo"
    repo.mkdir()
    init_repo(repo)
    
    # Create 3 commits
    import os
    orig_cwd = os.getcwd()
    os.chdir(repo)
    try:
        for i in range(3):
            f = repo / f"file_{i}.txt"
            f.write_text(f"content {i}")
            main(["add", str(f)])
            main(["commit", "-m", f"commit {i}"])
    finally:
        os.chdir(orig_cwd)
        
    port = get_free_port()
    proc = multiprocessing.Process(target=start_dashboard, args=(repo, "127.0.0.1", port))
    proc.daemon = True
    proc.start()
    
    # Wait for server
    import requests
    max_retries = 20
    while max_retries > 0:
        try:
            requests.get(f"http://127.0.0.1:{port}/api/status")
            break
        except:
            time.sleep(0.5)
            max_retries -= 1
            
    yield port, repo
    
    proc.terminate()
    proc.join()
