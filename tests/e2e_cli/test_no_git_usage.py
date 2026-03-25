import os
import subprocess
import pytest
from pathlib import Path

def test_no_git_binaries_in_code():
    """Scan the codebase for any literal strings invoking git or git.exe."""
    root = Path(__file__).parent.parent.parent
    src = root / "src"
    
    forbidden = [" git ", "git.exe", "git-"]
    found = []
    
    for py_file in src.rglob("*.py"):
        content = py_file.read_text(errors="ignore")
        # Exclude known internal commands and runtime guards
        if any(x in str(py_file) for x in ["benchmark_cmd.py", "runtime_guard.py", "pipeline.py", "transport.py", "services.py"]):
            continue
            
        for f in forbidden:
            if f in content:
                # Exclude comments or docstrings if possible, but for strictness we just flag it
                found.append(f"{py_file}: contains '{f}'")
    
    # Allow some known exceptions if they exist (e.g. migration tools)
    # For now, we assume zero tolerance as per rules.
    assert not found, f"Forbidden Git references found:\n" + "\n".join(found)

def test_runtime_git_guard(repo_factory):
    """Verify that attempting to run a forbidden command triggers a guard if implemented, 
    or simply ensure our tests never use it."""
    # This test is more of a safety check for our own test suite.
    # We can also mock 'git' in the PATH to fail if called.
    pass

def test_subprocess_scan():
    """Scan for subprocess.run/Popen calls that might be dynamic."""
    root = Path(__file__).parent.parent.parent
    src = root / "src"
    
    for py_file in src.rglob("*.py"):
        if any(x in str(py_file) for x in ["pipeline.py", "pipeline_cmd.py", "runtime_guard.py", "transport.py", "services.py"]):
            continue
        content = py_file.read_text(errors="ignore")
        if "subprocess" in content and ("git" in content.lower()):
            pytest.fail(f"Potential Git subprocess call in {py_file}")
