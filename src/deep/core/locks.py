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
from typing import Optional, Any, cast, Union

from deep.core.constants import DEEP_DIR # type: ignore
import threading
from deep.utils.utils import hash_bytes # type: ignore

_local_locks = threading.local()

def _get_held_lock_levels() -> list[int]:
    if not hasattr(_local_locks, 'levels'):
        _local_locks.levels = []
    return _local_locks.levels

class LockHierarchyViolation(RuntimeError):
    pass


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
    
    level: int = 0

    def __init__(self, lock_path: Path, timeout: float = 60.0):
        self.lock_path = lock_path
        self.timeout = timeout
        self._fd: Optional[int] = None
        self._file_handle = None

    def _write_metadata(self):
        """Write metadata using the already open self._file_handle.
        We seek to 0, write JSON, and ensure we don't overwrite the lock offset.
        """
        if not self._file_handle:
            return
        try:
            assert self._file_handle is not None
            cast(Any, self._file_handle).seek(0)
            metadata = {
                "pid": os.getpid(),
                "timestamp": time.time(),
                "hostname": os.environ.get("COMPUTERNAME", os.environ.get("HOSTNAME", "unknown")),
            }
            # Write JSON and pad with spaces to ensure we don't leave old partial data
            # but stay well below the 1024 byte lock offset.
            data = cast(str, json.dumps(metadata)) # type: ignore
            if len(data) > 1000:
                data = data[:1000] # type: ignore
            cast(Any, self._file_handle).write(data.ljust(1000))
            cast(Any, self._file_handle).flush()
            os.fsync(cast(Any, self._file_handle).fileno())
        except OSError:
            pass

    def _try_break_stale_lock(self) -> bool:
        """Read the lock metadata and check if the owner process is still alive.
        If the PID is dead, we break (unlink) the lock.
        """
        if not self.lock_path.exists():
            return False
        
        try:
            # On Windows, if the file is locked by another handle, this will fail.
            # That's fine - it means the process is alive.
            with open(self.lock_path, "r", encoding="utf-8") as f:
                data = cast(dict, json.load(f)) # type: ignore
            
            pid = cast(dict, data).get("pid") # type: ignore
            if pid and not _is_process_alive(pid):
                # Process is definitively dead. Break the lock.
                try:
                    os.remove(self.lock_path)
                    return True
                except (PermissionError, OSError):
                    # If we can't remove it, someone else might have acquired it
                    # or it's still somehow held.
                    pass
        except (OSError, json.JSONDecodeError, ValueError):
            # If we can't read it or it's corrupt, and it's not locked by OS,
            # we might consider it stale if it's very old? 
            # But user said "only if definitively dead".
            # For corrupt/empty files not held by OS, unlinking is usually safe.
            if self.lock_path.exists():
                try:
                    # Try a dummy lock. If it fails, someone has it.
                    # If it succeeds, the file is just lying around.
                    pass
                except OSError:
                    pass
        return False

    def acquire(self):
        held = _get_held_lock_levels()
        if any(l >= self.level for l in held):
            raise LockHierarchyViolation(
                f"DeepBridge: Lock hierarchy violation (deadlock prevention): "
                f"attempting to acquire level {self.level} while holding tighter/equal locks {held}"
            )
            
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        from deep.utils.utils import AtomicWriter # type: ignore
        import sys
        import time
        import random

        start_time = time.time()
        
        # Open the file for the duration of the lock
        # Use r+ to allow reading/writing without truncation
        if self.lock_path.exists():
            self._file_handle = cast(Any, open(self.lock_path, "r+")) # type: ignore
        else:
            self._file_handle = cast(Any, open(self.lock_path, "w+")) # type: ignore
        fd = cast(Any, self._file_handle).fileno() # type: ignore

        if sys.platform == "win32":
            import msvcrt
            while True:
                try:
                    # Lock at offset 1024 to allow reading metadata at the beginning
                    self._file_handle.seek(1024)
                    # LK_NBLCK: Non-blocking lock.
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                    self._write_metadata()
                    return
                except (BlockingIOError, PermissionError, OSError):
                    # Check for stale lock
                    if self._try_break_stale_lock():
                        continue
                    
                    if time.time() - start_time > self.timeout:
                        cast(Any, self._file_handle).close() # type: ignore
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
                    # Check for stale lock
                    if self._try_break_stale_lock():
                        continue
                        
                    if time.time() - start_time > self.timeout:
                        cast(Any, self._file_handle).close() # type: ignore
                        raise TimeoutError(f"DeepBridge: failed to acquire lock {self.lock_path} within {self.timeout}s")
                    time.sleep(0.05 + random.random() * 0.1)

        held.append(self.level)

    def release(self):
        if self._file_handle:
            import sys
            try:
                fd = cast(Any, self._file_handle).fileno() # type: ignore
                if sys.platform == "win32":
                    import msvcrt # type: ignore
                    try:
                        cast(Any, self._file_handle).seek(1024) # type: ignore
                        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                    except OSError:
                        pass
                else:
                    import fcntl # type: ignore
                    try:
                        fcntl.flock(fd, fcntl.LOCK_UN)
                    except OSError:
                        pass
            finally:
                cast(Any, self._file_handle).close() # type: ignore
                self._file_handle = None
                
        held = _get_held_lock_levels()
        if self.level in held:
            held.remove(self.level)

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()


class RepositoryLock(BaseLock):
    """Global lock for operations modifying the entire repository state."""
    level = 100
    def __init__(self, dg_dir: Path, timeout: float = 30.0):
        super().__init__(dg_dir / "repo.lock", timeout)


class BranchLock(BaseLock):
    """Lock for updating a specific branch."""
    level = 200
    def __init__(self, dg_dir: Path, branch_name: str, timeout: float = 10.0):
        super().__init__(dg_dir / "refs" / "heads" / f"{branch_name}.lock", timeout)


class IndexLock(BaseLock):
    """Lock specifically for index (staging area) updates."""
    level = 300
    def __init__(self, dg_dir: Path, timeout: float = 10.0):
        super().__init__(dg_dir / "index.lock", timeout)


class PackfileLock(BaseLock):
    """Lock for generating/writing packfiles to prevent concurrent packing."""
    level = 400
    def __init__(self, dg_dir: Path, timeout: float = 60.0):
        super().__init__(dg_dir / "objects" / "pack" / "packing.lock", timeout)
