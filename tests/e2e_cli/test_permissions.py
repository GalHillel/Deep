import pytest
import os
import sys
from pathlib import Path

@pytest.mark.skipif(sys.platform == "win32", reason="chmod bits behave differently on Windows")
def test_executable_bit_preservation(repo_factory):
    """Verify executable bit is preserved across commits (Unix only)."""
    path = repo_factory.create()
    f = path / "script.sh"
    f.write_text("#!/bin/sh")
    
    # Set +x
    os.chmod(f, 0o755)
    repo_factory.run(["add", "script.sh"], cwd=path)
    repo_factory.run(["commit", "-m", "add script"], cwd=path)
    
    # Checkout elsewhere
    clone = Path(tempfile.mkdtemp())
    repo_factory.run(["clone", str(path), str(clone)])
    assert os.access(clone / "script.sh", os.X_OK)
    shutil.rmtree(clone)

def test_readonly_file_flow(repo_factory):
    """Verify system handles read-only files gracefully."""
    path = repo_factory.create()
    f = path / "readonly.txt"
    f.write_text("v1")
    repo_factory.run(["add", "readonly.txt"], cwd=path)
    repo_factory.run(["commit", "-m", "v1"], cwd=path)
    
    # Make read-only
    os.chmod(f, 0o444)
    # Deep should still be able to diff or show it (read operation)
    res = repo_factory.run(["diff"], cwd=path)
    assert res.returncode == 0
    
    # Try to modify (should fail at OS level, check if deep handles it)
    res = repo_factory.run(["status"], cwd=path)
    assert res.returncode == 0
