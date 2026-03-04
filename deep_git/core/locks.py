"""
deep_git.core.locks
~~~~~~~~~~~~~~~~~~~
Cross-platform file locking primitives for repository operations.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Optional


class BaseLock:
    """A cross-platform process-level file lock using O_CREAT | O_EXCL."""

    def __init__(self, lock_path: Path, timeout: float = 10.0):
        self.lock_path = lock_path
        self.timeout = timeout
        self._fd: Optional[int] = None

    def acquire(self):
        start_time = time.time()
        while True:
            try:
                # O_CREAT | O_EXCL ensures atomic creation.
                self._fd = os.open(str(self.lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                # Lock acquired
                return
            except FileExistsError:
                if time.time() - start_time > self.timeout:
                    raise TimeoutError(f"Failed to acquire lock {self.lock_path} within {self.timeout}s")
                time.sleep(0.1)
            except OSError as e:
                # On Windows, PermissionError might be raised if another process is holding the file
                # or creating it. We treat it as lock contention if it exists.
                if self.lock_path.exists():
                    if time.time() - start_time > self.timeout:
                        raise TimeoutError(f"Failed to acquire lock {self.lock_path} within {self.timeout}s")
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
