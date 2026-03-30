import pytest
import time
import urllib.request
import urllib.error
from .conftest import get_free_port, poll_until

def test_studio_dashboard_process(repo_factory):
    """Start `deep studio` as a subprocess and verify endpoint responsiveness."""
    path = repo_factory.create("studio_test")
    port = get_free_port()
    
    # Start studio server
    web_proc = repo_factory.spawn(["studio", "--port", str(port)], cwd=path)
    
    url = f"http://localhost:{port}/"
    
    def check_studio():
        try:
            with urllib.request.urlopen(url, timeout=0.1) as response:
                return response.getcode() == 200
        except:
            return False
            
    # Poll until server is up
    assert poll_until(check_studio, timeout=10), "Studio dashboard failed to start"
    
    # Check content
    try:
        with urllib.request.urlopen(url) as response:
            content = response.read().decode("utf-8")
            assert "Deep" in content or "Studio" in content
    except Exception as e:
        pytest.fail(f"Studio server request failed: {e}")
    finally:
        web_proc.terminate()
        web_proc.wait(timeout=5)
