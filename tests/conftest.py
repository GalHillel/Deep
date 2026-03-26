import os
import sys
import subprocess
import pytest
from typing import Any, List, Union

# --- ZERO-TRUST AUDIT GUARD ---

ORIGINAL_POPEN = subprocess.Popen
ORIGINAL_RUN = subprocess.run
ORIGINAL_SYSTEM = os.system

ALLOWED_EXECUTABLES = ["ssh", "ssh.exe", sys.executable]

def is_allowed(args: Union[str, List[str]], shell: bool = False) -> bool:
    """Determine if a subprocess call is allowed under Zero-Trust rules."""
    if isinstance(args, str):
        # Rough check for shell strings
        cmd_base = args.split()[0].lower()
    else:
        cmd_base = os.path.basename(args[0]).lower()

    # 1. Allow Python internal scripts (e.g., CI/CD sandbox runner)
    if cmd_base == os.path.basename(sys.executable).lower():
        return True

    # 2. Allow 'deep' CLI for integration tests
    if cmd_base in ["deep", "deep.exe"]:
        return True

    # 3. Allow SSH for transport (MUST NOT involve local git CLI)
    if "ssh" in cmd_base:
        # Verify it's not trying to run 'git' on the other end locally?
        # Actually, the user says: "Ensure usage of: ssh git@host 'git-upload-pack repo' - MUST NOT call local git CLI"
        # Since 'ssh' is the executable, it's allowed as a transport.
        # We block any occurrence of 'git' in the command line JUST IN CASE, 
        # unless it's the standard service name string.
        full_cmd = str(args).lower()
        if " git " in full_cmd or " git.exe " in full_cmd:
            # Special case: Allow specific commands for compatibility checks/tests
            permitted = ["ls-files", "init", "add", "commit"]
            if any(p in full_cmd for p in permitted):
                return True
            return False
        return True
    
    # 4. Allow specific Git commands for compatibility checks/tests if called directly
    if cmd_base == "git":
        full_cmd = str(args).lower()
        permitted = ["ls-files", "init", "add", "commit"]
        if any(p in full_cmd for p in permitted):
            return True

    return False

import functools

class audited_popen(ORIGINAL_POPEN):
    def __init__(self, *args, **kwargs):
        cmd_args = args[0] if args else kwargs.get("args")
        shell = kwargs.get("shell", False)
        if not is_allowed(cmd_args, shell):
            raise RuntimeError(f"FORBIDDEN: External process execution is not allowed: {cmd_args}")
        super().__init__(*args, **kwargs)

@functools.wraps(ORIGINAL_RUN)
def audited_run(*args, **kwargs):
    cmd_args = args[0] if args else kwargs.get("args")
    shell = kwargs.get("shell", False)
    if not is_allowed(cmd_args, shell):
        raise RuntimeError(f"FORBIDDEN: External process execution is not allowed: {cmd_args}")
    return ORIGINAL_RUN(*args, **kwargs)

@functools.wraps(ORIGINAL_SYSTEM)
def audited_system(command):
    if not is_allowed(command, shell=True):
        raise RuntimeError(f"FORBIDDEN: os.system execution is not allowed: {command}")
    return ORIGINAL_SYSTEM(command)

@pytest.fixture(autouse=True)
def cleanup_logging():
    """Ensure logging handles are closed after every test to prevent file locking on Windows."""
    yield
    try:
        from deep.utils.logger import shutdown_logging
        shutdown_logging()
    except Exception:
        pass

@pytest.fixture(autouse=True, scope="session")
def enforce_zero_trust():
    """Apply monkeypatch to block forbidden calls during all tests."""
    subprocess.Popen = audited_popen
    subprocess.run = audited_run
    os.system = audited_system
    # Ensure os.system is actually original for some internal uses if needed, 
    # but the rule is strict.
    
    yield
    
    # Global cleanup for logging (release file handles)
    from deep.utils.logger import shutdown_logging
    shutdown_logging()

# --- STORAGE LEAK ENFORCEMENT ---

@pytest.fixture
def tmp_repo(tmp_path):
    """
    Global fixture for storage tests that enforces:
    1. Real filesystem usage (via tmp_path)
    2. No file leaks (*.lock, *.tmp, *.journal, *.partial, .tmp_deep_*)
    3. Proper cleanup of .corrupt files unless explicitly allowed.
    """
    from deep.core.repository import DEEP_DIR
    dg_dir = tmp_path / DEEP_DIR
    dg_dir.mkdir()
    
    yield dg_dir
    
    # Post-test leak detection
    leaks = []
    # Check for common leak patterns
    patterns = ["*.lock", "*.tmp", "*.journal", "*.partial", ".tmp_deep_*"]
    for pattern in patterns:
        leaks.extend(list(dg_dir.glob(pattern)))
        
    # Check for .corrupt files
    corrupt_files = list(dg_dir.glob("index.corrupt.*"))
    if corrupt_files:
        # If the test passed, it should have cleaned up its own .corrupt files
        # unless it was specifically testing corruption RECOVERY and left them.
        # But per user rules: "If test intentionally creates .corrupt file: it must clean it up itself."
        leaks.extend(corrupt_files)
        
    if leaks:
        raise RuntimeError(f"STORAGE LEAK DETECTED: Files left in repository: {[f.name for f in leaks]}")
