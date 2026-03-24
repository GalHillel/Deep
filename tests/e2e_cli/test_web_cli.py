import pytest
import time
import urllib.request
import urllib.error
from .conftest import get_free_port, poll_until

def test_web_dashboard_process(repo_factory):
    """Start `deep web` as a subprocess and verify endpoint responsiveness."""
    path = repo_factory.create("web_test")
    port = get_free_port()
    
    # Start web server
    web_proc = repo_factory.spawn(["web", "--port", str(port)], cwd=path)
    
    url = f"http://localhost:{port}/"
    
    def check_web():
        try:
            with urllib.request.urlopen(url, timeout=0.1) as response:
                return response.getcode() == 200
        except:
            return False
            
    # Poll until server is up
    assert poll_until(check_web, timeout=10), "Web dashboard failed to start"
    
    # Check content
    try:
        with urllib.request.urlopen(url) as response:
            content = response.read().decode("utf-8")
            assert "Deep" in content or "Dashboard" in content
    except Exception as e:
        pytest.fail(f"Web server request failed: {e}")
    finally:
        web_proc.terminate()
        web_proc.wait(timeout=5)
