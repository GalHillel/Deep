"""
deep.core.locks
~~~~~~~~~~~~~~~~~~~
Cross-platform file locking primitives for DeepBridge repository operations.

Includes stale lock detection: if a lock file contains PID+timestamp metadata
and the owning process no longer exists, the lock is automatically broken.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Optional


# Stale lock threshold: if a lock is older than this and its PID is dead, break it.
STALE_LOCK_THRESHOLD_SECONDS = 300  # 5 minutes


def _is_process_alive(pid: int) -> bool:
    """Check if a process with the given PID is still alive."""
    if pid <= 0:
        return False
    
    import sys
    if sys.platform == "win32":
        import ctypes
        # Process existence + activity check on Windows
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if handle:
            exit_code = ctypes.c_ulong()
            ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
            ctypes.windll.kernel32.CloseHandle(handle)
            return exit_code.value == STILL_ACTIVE
        return False
    else:
        try:
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError):
            return False
        except PermissionError:
            return True


class BaseLock:
    """A cross-platform process-level file lock using O_CREAT | O_EXCL.

    Lock files contain JSON metadata with the owning PID and creation timestamp,
    enabling stale lock detection and automatic cleanup.
    """

    def __init__(self, lock_path: Path, timeout: float = 10.0):
        self.lock_path = lock_path
        self.timeout = timeout
        self._fd: Optional[int] = None

    def _write_metadata(self):
        """Write PID and timestamp metadata into the lock file."""
        if self._fd is not None:
            metadata = json.dumps({
                "pid": os.getpid(),
                "timestamp": time.time(),
                "hostname": os.environ.get("COMPUTERNAME", os.environ.get("HOSTNAME", "unknown")),
            }).encode("utf-8")
            try:
                os.write(self._fd, metadata)
            except OSError:
                pass  # Lock file already created, metadata is best-effort

    def _try_break_stale_lock(self) -> bool:
        """Attempt to break a stale lock. Returns True if the lock was broken."""
        try:
            if not self.lock_path.exists():
                return False
            try:
                data = self.lock_path.read_text(encoding="utf-8")
            except (OSError, PermissionError):
                # Sharing violation on Windows or other disk error
                data = ""
            
            if not data.strip():
                # Empty lock file — check age instead
                age = time.time() - self.lock_path.stat().st_mtime
                if age > STALE_LOCK_THRESHOLD_SECONDS:
                    self.lock_path.unlink()
                    return True
                return False

            meta = json.loads(data)
            pid = meta.get("pid", 0)
            ts = meta.get("timestamp", 0)

            # If the PID is dead, break the lock
            if pid and not _is_process_alive(pid):
                self.lock_path.unlink()
                return True

            # If the lock is very old (even if PID still exists), break it
            if ts and (time.time() - ts) > STALE_LOCK_THRESHOLD_SECONDS:
                self.lock_path.unlink()
                return True

        except (OSError, json.JSONDecodeError, ValueError):
            # If we can't read/parse the metadata, try age-based check
            try:
                age = time.time() - self.lock_path.stat().st_mtime
                if age > STALE_LOCK_THRESHOLD_SECONDS:
                    self.lock_path.unlink()
                    return True
            except OSError:
                pass
        return False

    def acquire(self):
        start_time = time.time()
        stale_check_done = False
        while True:
            try:
                # O_CREAT | O_EXCL ensures atomic creation.
                self._fd = os.open(str(self.lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                self._write_metadata()
                return
            except FileExistsError:
                # Try to break stale lock once per acquire attempt
                if not stale_check_done:
                    stale_check_done = True
                    if self._try_break_stale_lock():
                        continue  # Retry immediately after breaking stale lock

                if time.time() - start_time > self.timeout:
                    raise TimeoutError(f"DeepBridge: failed to acquire lock {self.lock_path} within {self.timeout}s")
                time.sleep(0.1)
            except OSError as e:
                # On Windows, PermissionError might be raised if another process is
                # holding the file. Treat as contention if it exists.
                if self.lock_path.exists():
                    if not stale_check_done:
                        stale_check_done = True
                        if self._try_break_stale_lock():
                            continue

                    if time.time() - start_time > self.timeout:
                        raise TimeoutError(f"DeepBridge: failed to acquire lock {self.lock_path} within {self.timeout}s")
                    time.sleep(0.1)
                else:
                    raise e

    def release(self):
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None
            try:
                self.lock_path.unlink()
            except OSError:
                pass

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()


class RepositoryLock(BaseLock):
    """Global lock for operations modifying the entire repository state."""
    def __init__(self, dg_dir: Path, timeout: float = 30.0):
        super().__init__(dg_dir / "index.lock", timeout)


class BranchLock(BaseLock):
    """Lock for updating a specific branch."""
    def __init__(self, dg_dir: Path, branch_name: str, timeout: float = 10.0):
        super().__init__(dg_dir / "refs" / "heads" / f"{branch_name}.lock", timeout)


class PackfileLock(BaseLock):
    """Lock for generating/writing packfiles to prevent concurrent packing."""
    def __init__(self, dg_dir: Path, timeout: float = 60.0):
        super().__init__(dg_dir / "objects" / "pack" / "packing.lock", timeout)
