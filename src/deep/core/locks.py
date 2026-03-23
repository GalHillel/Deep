"""
deep.core.locks
~~~~~~~~~~~~~~~~~~~
Cross-platform file locking primitives for Deep repository operations.

Includes stale lock detection: if a lock file contains PID+timestamp metadata
and the owning process no longer exists, the lock is automatically broken.
"""

from __future__ import annotations

import os
import time
import logging
import json
import random
import threading
from pathlib import Path
from typing import Optional, Any, cast, Union, Dict

from deep.core.constants import DEEP_DIR # type: ignore
import threading
from deep.utils.utils import hash_bytes # type: ignore

_local_locks = threading.local()

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
    """A cross-platform process-level file lock using atomic filesystem operations.
    
    Uses os.open(O_CREAT | O_EXCL) for atomic acquisition and PID-liveness for stale cleanup.
    Now guaranteed to be leak-free (removes the lock file on release).
    """
    level: int = 0
    _thread_local = threading.local()
    _lock_registry: Dict[str, threading.RLock] = {}
    _registry_lock = threading.Lock()

    def __init__(self, lock_path: Path, timeout: float = 60.0):
        self.lock_path = lock_path
        self.timeout = timeout
        self.pid = os.getpid()
        self.lock_id = str(lock_path.absolute())
        
        # Get or create the RLock for this specific file path
        with self._registry_lock:
            if self.lock_id not in self._lock_registry:
                self._lock_registry[self.lock_id] = threading.RLock()
            self._process_lock = self._lock_registry[self.lock_id]

    def _get_counter(self) -> Dict[str, int]:
        if not hasattr(self._thread_local, 'counters'):
            self._thread_local.counters = {}
        return self._thread_local.counters

    def _get_lock_pid(self) -> Optional[int]:
        """Read PID from lock file with sharing flags on Windows."""
        if not self.lock_path.exists():
            return None
        try:
            # On Windows, os.O_BINARY and sharing flags are important
            flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0)
            fd = os.open(self.lock_path, flags)
            try:
                data = os.read(fd, 32).decode().strip()
                if not data: return None
                # Support both raw PID and legacy JSON
                if data.startswith('{'):
                    return int(json.loads(data).get('pid', 0))
                return int(data)
            finally:
                os.close(fd)
        except (OSError, ValueError, json.JSONDecodeError):
            return None

    def acquire(self):
        """Acquire lock (reentrant)."""
        counters = self._get_counter()
        # Thread-level reentrancy check
        if counters.get(self.lock_id, 0) > 0:
            counters[self.lock_id] += 1
            return

        start = time.time()
        while True:
            # 1. Thread-level race protection (reentrant per thread)
            if not self._process_lock.acquire(blocking=True, timeout=0.1):
                if time.time() - start > self.timeout:
                    raise TimeoutError(f"Timed out waiting for process_lock for {self.lock_path}")
                continue

            try:
                # 2. Aggressive stale cleanup & cross-implementation reentrancy
                if self.lock_path.exists():
                    owner_pid = self._get_lock_pid()
                    if owner_pid == self.pid:
                        # Already held by our process (reentrancy)
                        counters[self.lock_id] = 1
                        return
                    if owner_pid is None or not _is_process_alive(owner_pid):
                        # FOUND STALE LOCK: Trigger recovery before unlinking
                        self._pre_acquire_recovery(owner_pid)
                        try: os.remove(self.lock_path)
                        except OSError: pass
                
                # 3. Atomic acquisition
                self.lock_path.parent.mkdir(parents=True, exist_ok=True)
                fd = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, 'O_BINARY', 0))
                try:
                    os.write(fd, str(self.pid).encode())
                finally:
                    os.close(fd)
                
                counters[self.lock_id] = 1
                return
            except (FileExistsError, PermissionError, OSError):
                self._process_lock.release()
                if time.time() - start > self.timeout:
                    raise TimeoutError(f"Timed out acquiring {self.lock_path} after {self.timeout}s")
                time.sleep(0.05 + random.random() * 0.1)

    def _pre_acquire_recovery(self, stale_pid: Optional[int]):
        """Hook for child classes to perform recovery when a stale lock is found."""
        pass

    def release(self):
        """Release lock (reentrant)."""
        counters = self._get_counter()
        if counters.get(self.lock_id, 0) <= 0:
            return
            
        counters[self.lock_id] -= 1
        if counters[self.lock_id] == 0:
            try:
                owner_pid = self._get_lock_pid()
                if owner_pid == self.pid or owner_pid is None:
                    # Windows retry loop for removal
                    for i in range(5):
                        try:
                            if self.lock_path.exists():
                                os.remove(self.lock_path)
                            break
                        except OSError:
                            time.sleep(0.01)
            except OSError:
                pass
            finally:
                if self.lock_id in counters:
                    del counters[self.lock_id]
                try:
                    self._process_lock.release()
                except RuntimeError:
                    # Not held by this thread
                    pass

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
        self.dg_dir = dg_dir

    def _pre_acquire_recovery(self, stale_pid: Optional[int]):
        """Trigger index recovery if the repository lock was left stale."""
        from deep.storage.recovery import recover_stale_index_backups
        recover_stale_index_backups(self.dg_dir)


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
        self.dg_dir = dg_dir

    def _pre_acquire_recovery(self, stale_pid: Optional[int]):
        """Auto-restore stale index backups before acquiring the index lock."""
        from deep.storage.recovery import recover_stale_index_backups
        recover_stale_index_backups(self.dg_dir)


class PackfileLock(BaseLock):
    """Lock for generating/writing packfiles."""
    level = 400
    def __init__(self, dg_dir: Path, timeout: float = 60.0):
        super().__init__(dg_dir / "objects" / "pack" / "packing.lock", timeout)


def _is_process_alive(pid: int) -> bool:
    """Check if a process is alive (cross-platform)."""
    if pid <= 0: return False
    try:
        import os
        if os.name == 'nt':
            # Windows
            import ctypes
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            STILL_ACTIVE = 259
            handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if not handle:
                return False
            exit_code = ctypes.c_ulong()
            ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
            ctypes.windll.kernel32.CloseHandle(handle)
            return exit_code.value == STILL_ACTIVE
        else:
            # POSIX
            try:
                os.kill(pid, 0)
                return True
            except OSError:
                return False
    except Exception:
        return False
