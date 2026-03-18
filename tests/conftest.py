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

    # 2. Allow SSH for transport (MUST NOT involve local git CLI)
    if "ssh" in cmd_base:
        # Verify it's not trying to run 'git' on the other end locally?
        # Actually, the user says: "Ensure usage of: ssh git@host 'git-upload-pack repo' - MUST NOT call local git CLI"
        # Since 'ssh' is the executable, it's allowed as a transport.
        # We block any occurrence of 'git' in the command line JUST IN CASE, 
        # unless it's the standard service name string.
        full_cmd = str(args).lower()
        if " git " in full_cmd or " git.exe " in full_cmd:
            return False
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

@pytest.fixture(autouse=True, scope="session")
def enforce_zero_trust():
    """Apply monkeypatch to block forbidden calls during all tests."""
    subprocess.Popen = audited_popen
    subprocess.run = audited_run
    os.system = audited_system
    yield
    # Restore (optional, as processes usually exit after tests)
    subprocess.Popen = ORIGINAL_POPEN
    subprocess.run = ORIGINAL_RUN
    os.system = ORIGINAL_SYSTEM
