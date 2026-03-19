"""
deep.core.runtime_guard
~~~~~~~~~~~~~~~~~~~~~~~~~
Hardened runtime guard that intercepts and blocks forbidden VCS execution.

Protects against accidental or malicious invocation of external
version control tools via subprocess, os.system, or os.spawn.

Activated at import time via deep/__init__.py.
"""

from __future__ import annotations

import os
import subprocess
import sys
import functools
from typing import Any, Callable, Optional

# Forbidden patterns (case-insensitive substrings in command arguments)
_FORBIDDEN_PATTERNS = frozenset([
    "git ",
    "git.exe",
    "git\t",
    "git\n",
    "/git ",
    "\\git ",
    "\\git.exe",
    "/git.exe",
])

_GUARD_ACTIVE = False


def _contains_forbidden(cmd: Any) -> bool:
    """Check if a command string or list contains forbidden VCS tool references."""
    if cmd is None:
        return False

    # Normalize to a single lowercase string for scanning
    if isinstance(cmd, (list, tuple)):
        cmd_str = " ".join(str(c) for c in cmd).lower()
    else:
        cmd_str = str(cmd).lower()

    # Check exact matches for when the command IS the forbidden tool
    parts = cmd_str.split()
    if parts and parts[0].rstrip(".exe") in ("git",):
        return True

    # Check patterns
    for pattern in _FORBIDDEN_PATTERNS:
        if pattern in cmd_str:
            return True

    return False


def _guard_error(cmd: Any) -> RuntimeError:
    """Create a RuntimeError for forbidden command execution."""
    return RuntimeError(
        f"Deep RUNTIME GUARD: Blocked execution of forbidden VCS tool.\n"
        f"Command: {cmd!r}\n"
        f"Deep is fully independent and does not invoke external version control tools."
    )


# ── Patched functions ──────────────────────────────────────────────────

_original_popen_init: Optional[Callable] = None
_original_run: Optional[Callable] = None
_original_call: Optional[Callable] = None
_original_check_output: Optional[Callable] = None
_original_check_call: Optional[Callable] = None
_original_system: Optional[Callable] = None


def _guarded_popen_init(self: Any, args: Any, *a: Any, **kw: Any) -> None:
    if _contains_forbidden(args):
        raise _guard_error(args)
    assert _original_popen_init is not None
    return _original_popen_init(self, args, *a, **kw)


def _guarded_run(args: Any, *a: Any, **kw: Any) -> Any:
    if _contains_forbidden(args):
        raise _guard_error(args)
    assert _original_run is not None
    return _original_run(args, *a, **kw)


def _guarded_call(args: Any, *a: Any, **kw: Any) -> Any:
    if _contains_forbidden(args):
        raise _guard_error(args)
    assert _original_call is not None
    return _original_call(args, *a, **kw)


def _guarded_check_output(args: Any, *a: Any, **kw: Any) -> Any:
    if _contains_forbidden(args):
        raise _guard_error(args)
    assert _original_check_output is not None
    return _original_check_output(args, *a, **kw)


def _guarded_check_call(args: Any, *a: Any, **kw: Any) -> Any:
    if _contains_forbidden(args):
        raise _guard_error(args)
    assert _original_check_call is not None
    return _original_check_call(args, *a, **kw)


def _guarded_system(cmd: str) -> int:
    if _contains_forbidden(cmd):
        raise _guard_error(cmd)
    assert _original_system is not None
    return _original_system(cmd)


def _make_guarded_spawn(original: Callable, name: str) -> Callable:
    """Create a guarded wrapper for os.spawn* functions."""
    @functools.wraps(original)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        # For spawnl/spawnle/spawnlp/spawnlpe: args are (mode, file, *args)
        # For spawnv/spawnve/spawnvp/spawnvpe: args are (mode, file, args, ...)
        # Check the 'file' argument (index 1) and any arg list
        if len(args) >= 2:
            if _contains_forbidden(args[1]):
                raise _guard_error(args[1])
        if len(args) >= 3:
            if isinstance(args[2], (list, tuple)):
                if _contains_forbidden(args[2]):
                    raise _guard_error(args[2])
        return original(*args, **kwargs)
    return wrapper


def activate() -> None:
    """Activate the runtime guard. Called once at startup."""
    global _GUARD_ACTIVE
    global _original_popen_init, _original_run, _original_call
    global _original_check_output, _original_check_call, _original_system

    if _GUARD_ACTIVE:
        return

    # Patch subprocess
    _original_popen_init = subprocess.Popen.__init__
    _original_run = subprocess.run
    _original_call = subprocess.call
    _original_check_output = subprocess.check_output
    _original_check_call = subprocess.check_call
    _original_system = os.system

    subprocess.Popen.__init__ = _guarded_popen_init  # type: ignore
    subprocess.run = _guarded_run  # type: ignore
    subprocess.call = _guarded_call  # type: ignore
    subprocess.check_output = _guarded_check_output  # type: ignore
    subprocess.check_call = _guarded_check_call  # type: ignore
    os.system = _guarded_system  # type: ignore

    # Patch os.spawn* if they exist (mainly Unix, but also partial Windows)
    for spawn_name in (
        "spawnl", "spawnle", "spawnlp", "spawnlpe",
        "spawnv", "spawnve", "spawnvp", "spawnvpe",
    ):
        original = getattr(os, spawn_name, None)
        if original is not None:
            setattr(os, spawn_name, _make_guarded_spawn(original, spawn_name))

    _GUARD_ACTIVE = True


def deactivate() -> None:
    """Deactivate the runtime guard (for testing only)."""
    global _GUARD_ACTIVE
    global _original_popen_init, _original_run, _original_call
    global _original_check_output, _original_check_call, _original_system

    if not _GUARD_ACTIVE:
        return

    if _original_popen_init:
        subprocess.Popen.__init__ = _original_popen_init  # type: ignore
    if _original_run:
        subprocess.run = _original_run  # type: ignore
    if _original_call:
        subprocess.call = _original_call  # type: ignore
    if _original_check_output:
        subprocess.check_output = _original_check_output  # type: ignore
    if _original_check_call:
        subprocess.check_call = _original_check_call  # type: ignore
    if _original_system:
        os.system = _original_system  # type: ignore

    _GUARD_ACTIVE = False


def scan_source(source_dir: str) -> list[tuple[str, int, str]]:
    """Scan Python source files for forbidden word references.

    Returns list of (filepath, lineno, line_content) violations.
    """
    import re
    violations: list[tuple[str, int, str]] = []
    forbidden_re = re.compile(r'\bgit\b', re.IGNORECASE)

    # Whitelist patterns that are false positives
    # These are either: the guard's own pattern strings, wire protocol identifiers,
    # URL suffix checks, or HTTP header names required for interoperability.
    whitelist = [
        "digit",
        "legitimate",
        "# purge",
        "purge_forbidden",
        "purge_deepbridge",
        "runtime_guard",
        "forbidden",
        # Wire protocol service names (required for remote interop)
        "upload-pack",
        "receive-pack",
        # URL suffix handling
        '.git"',
        ".git'",
        ".git)",
        # HTTP header (standard protocol)
        "git-protocol",
        # Pattern matching code in this file
        "_forbidden_patterns",
        "_contains_forbidden",
        'rstrip(".exe")',
        "(\"git\",)",
        "\"git ",
        "\"git.",
        "\"git\\\\",
        "\"/git",
        "\"\\\\git",
        # Fix scripts
        "fix_remaining",
        # Self-referencing patterns in the guard (tab/newline variants)
        "\"git\\\\t\"",
        "\"git\\\\n\"",
    ]

    for root, dirs, files in os.walk(source_dir):
        # Skip __pycache__
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for fname in files:
            if not fname.endswith(".py"):
                continue
            # Skip this file (runtime_guard) — it inherently contains
            # the forbidden patterns as part of its blocking logic
            if fname == "runtime_guard.py":
                continue
            fpath = os.path.join(root, fname)
            try:
                with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                    for lineno, line in enumerate(f, 1):
                        if forbidden_re.search(line):
                            # Check whitelist
                            lower_line = line.lower()
                            if any(w in lower_line for w in whitelist):
                                continue
                            violations.append((fpath, lineno, line.rstrip()))
            except (OSError, UnicodeDecodeError):
                continue

    return violations
