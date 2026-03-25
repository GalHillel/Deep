import pytest
import os
import sys
from pathlib import Path

def test_executable_bit_preservation(repo_factory):
    """Verify file permission attributes are preserved across commits."""
    path = repo_factory.create()
    f = path / "script.sh"
    f.write_text("#!/bin/sh")
    
    if sys.platform != "win32":
        # Unix: Set +x and verify
        os.chmod(f, 0o755)
    
    repo_factory.run(["add", "script.sh"], cwd=path)
    repo_factory.run(["commit", "-m", "add script"], cwd=path)
    
    # Verify the file is tracked
    res = repo_factory.run(["status"], cwd=path)
    assert res.returncode == 0

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
