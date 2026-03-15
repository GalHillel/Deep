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
    """A cross-platform process-level file lock using native OS primitives.
    
    Uses msvcrt.locking on Windows and fcntl.flock on Unix.
    """

    def __init__(self, lock_path: Path, timeout: float = 60.0):
        self.lock_path = lock_path
        self.timeout = timeout
        self._fd: Optional[int] = None
        self._file_handle = None

    def _write_metadata(self):
        """Best-effort metadata update. Since we use advisory locks, 
        the file stays on disk. We just overwrite the metadata.
        """
        try:
            with open(self.lock_path, "w", encoding="utf-8") as f:
                json.dump({
                    "pid": os.getpid(),
                    "timestamp": time.time(),
                    "hostname": os.environ.get("COMPUTERNAME", os.environ.get("HOSTNAME", "unknown")),
                }, f)
        except OSError:
            pass

    def _try_break_stale_lock(self) -> bool:
        """With native advisory locks, if the process dies, the OS 
        automatically releases the lock. Stale lock breaking is handled 
        by the OS. We keep this as a no-op for API compatibility.
        """
        return False

    def acquire(self):
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        import sys
        import time
        import random

        start_time = time.time()
        
        # Open the file for the duration of the lock
        self._file_handle = open(self.lock_path, "a")
        fd = self._file_handle.fileno()

        if sys.platform == "win32":
            import msvcrt
            while True:
                try:
                    # LK_NBLCK: Non-blocking lock. If fail, we retry with our own timeout/jitter.
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                    self._write_metadata()
                    return
                except (BlockingIOError, PermissionError, OSError):
                    if time.time() - start_time > self.timeout:
                        self._file_handle.close()
                        raise TimeoutError(f"DeepBridge: failed to acquire lock {self.lock_path} within {self.timeout}s")
                    time.sleep(0.05 + random.random() * 0.1)
        else:
            import fcntl
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    self._write_metadata()
                    return
                except (BlockingIOError, OSError):
                    if time.time() - start_time > self.timeout:
                        self._file_handle.close()
                        raise TimeoutError(f"DeepBridge: failed to acquire lock {self.lock_path} within {self.timeout}s")
                    time.sleep(0.05 + random.random() * 0.1)

    def release(self):
        if self._file_handle:
            import sys
            try:
                fd = self._file_handle.fileno()
                if sys.platform == "win32":
                    import msvcrt
                    try:
                        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                    except OSError:
                        pass
                else:
                    import fcntl
                    try:
                        fcntl.flock(fd, fcntl.LOCK_UN)
                    except OSError:
                        pass
            finally:
                self._file_handle.close()
                self._file_handle = None
                # Optional: unlink if we are the only ones. 
                # But for WAL/Index it's often better to just leave the empty file.

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
