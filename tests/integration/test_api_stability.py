import pytest
import requests
import multiprocessing
import time
import shutil
from deep.web.dashboard import start_dashboard
from deep.core.repository import init_repo

import socket

def get_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]

@pytest.fixture(scope="module")
def repo_with_server(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("api_stability")
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)
    
    port = get_free_port()
    base_url = f"http://127.0.0.1:{port}"
    
    # Start server in a background process
    proc = multiprocessing.Process(target=start_dashboard, args=(repo, "127.0.0.1", port))
    proc.daemon = True
    proc.start()
    
    # Wait for server to be ready
    max_retries = 20
    while max_retries > 0:
        try:
            requests.get(f"{base_url}/api/health")
            break
        except Exception:
            time.sleep(0.5)
            max_retries -= 1
            
    yield repo, base_url
    
    proc.terminate()
    proc.join()

@pytest.mark.parametrize("path,method,data", [
    ("/api/health", "GET", None),
    ("/api/tree", "GET", None),
    ("/api/work", "GET", None),
    ("/api/file?path=non_existent_file.txt", "GET", None),
    ("/api/commit", "POST", {"author": "Test", "message": "Test commit"}),
])
def test_endpoint(repo_with_server, path, method, data):
    repo, base_url = repo_with_server
    url = f"{base_url}{path}"
    print(f"Testing {method} {path}...")
    if method == "GET":
        resp = requests.get(url)
    else:
        resp = requests.post(url, json=data)
    
    print(f"  Status: {resp.status_code}")
    try:
        res_json = resp.json()
        print(f"  Success: {res_json.get('success')}")
    except:
        print(f"  Response is not JSON: {resp.text[:100]}")

