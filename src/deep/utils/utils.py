"""
deep.utils.utils
~~~~~~~~~~~~~~~~

Core system utilities: Atomic I/O, hashing, and date formatting.

This module provides the low-level primitives required for a crash-safe 
and consistent storage engine. All sensitive file writes should use 
`AtomicWriter` to prevent partial data corruption.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
import unicodedata
import re
from pathlib import Path
from typing import List, Optional, Union, IO, Any, TYPE_CHECKING, cast, Tuple

if TYPE_CHECKING:
    from deep.core.locks import BaseLock # type: ignore[import]


class DeepError(Exception):
    """Base exception for all Deep errors."""
    pass


def hash_bytes(data: bytes) -> str:
    """Return the hex-encoded SHA-1 hash of *data*.

    SHA-1 is used for the content-addressable storage scheme. 
    The 40-character lowercase hex digest is returned.

    Args:
        data: Raw bytes to hash.

    Returns:
        40-character lowercase hex SHA-1 digest.
    """
    return hashlib.sha1(data).hexdigest()


class AtomicWriter:
    """Context manager that writes data to a file atomically.

    Usage::

        with AtomicWriter(target_path) as aw:
            aw.write(b"some data")

    On successful exit the temp file is flushed, fsynced, and atomically
    moved to *target_path* via :func:`os.replace`.  If an exception is
    raised inside the context the temp file is removed and the target is
    left untouched.

    Args:
        target: Destination path (str or :class:`~pathlib.Path`).
        mode: File mode string (``"wb"`` for binary, ``"w"`` for text).
    """

    def __init__(self, target: Union[str, Path], mode: str = "wb") -> None:
        self.target = Path(target)
        self.original_mode = mode
        self.mode = mode
        self._tmp_path: Optional[Path] = None
        self._file: Optional[IO[Any]] = None
        self._fd: Optional[int] = None
        self._is_append = "a" in mode
        self._lock: Optional[BaseLock] = None

    def __enter__(self) -> "AtomicWriter":
        self.target.parent.mkdir(parents=True, exist_ok=True)
        
        if self._is_append:
            # Native append is atomic for small writes (like WAL records)
            from deep.core.locks import BaseLock
            self._lock = BaseLock(self.target.with_suffix(".lock"))
            self._lock.acquire()
            
            flags = os.O_APPEND | os.O_CREAT | os.O_WRONLY | getattr(os, 'O_BINARY', 0)
            self._fd = os.open(self.target, flags)
            self._file = os.fdopen(self._fd, self.mode, encoding="utf-8" if 'b' not in self.mode else None)
            return self

        fd, tmp_name = tempfile.mkstemp(
            dir=str(self.target.parent),
            prefix=f".tmp_deep_{os.getpid()}_",
        )
        self._fd = fd
        self._tmp_path = Path(tmp_name)
        self._file = os.fdopen(cast(int, self._fd), self.mode)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:  # type: ignore[override]
        try:
            if self._file:
                if exc_type is not None:
                    cast(Any, self._file).close() # type: ignore
                    if self._tmp_path.exists():
                        cast(Any, self._tmp_path).unlink() # type: ignore
                    return

                cast(Any, self._file).flush() # type: ignore
                if self._fd is not None:
                    try:
                        os.fsync(cast(int, self._fd))
                    except OSError:
                        pass
                self._file.close() # type: ignore
                self._file = None
                
                if self._tmp_path is not None:
                    # Atomic swap with robust retry for Windows (WinError 5: Access is denied)
                    max_retries = 30
                    for i in range(max_retries):
                        try:
                            os.replace(str(self._tmp_path), str(self.target))
                            break
                        except (OSError, PermissionError):
                            # On Windows, os.replace can fail if the destination is being 
                            # read/locked by another process or if deletion is pending.
                            if i == max_retries - 1:
                                raise
                            # Randomized exponential backoff
                            time.sleep(0.01 * (i + 1) + 0.05 * (i % 2))
        finally:
            # Always ensure the lock is released if it was acquired
            if hasattr(self, "_lock") and self._lock:
                self._lock.release() # type: ignore
                self._lock = None
        
        # Fsync the parent directory to ensure the directory entry is persisted
        try:
            if sys.platform != "win32":
                dir_fd = os.open(str(self.target.parent), os.O_RDONLY)
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
        except OSError:
            # Ignoring directory fsync errors, particularly on systems where 
            # opening a directory for reading is restricted (like Windows without specific flags).
            pass

    # ------------------------------------------------------------------
    # Writing helpers
    # ------------------------------------------------------------------

    def write(self, data: Union[bytes, str]) -> int:
        """Write *data* to the underlying temporary file.

        Returns:
            Number of bytes/characters written.
        """
        return self._file.write(data)  # type: ignore[union-attr]


def get_local_timezone_offset() -> str:
    """Return local timezone offset in +HHMM format."""
    import time
    if time.localtime().tm_isdst and time.daylight:
        offset = -time.altzone
    else:
        offset = -time.timezone
    
    hours, remainder = divmod(abs(offset), 3600)
    minutes = remainder // 60
    sign = "+" if offset >= 0 else "-"
    return f"{sign}{hours:02d}{minutes:02d}"


def format_date(timestamp: int, tz_offset_str: str) -> str:
    """Format a Unix timestamp and tz offset into a readable date string.
    Example: 'Tue Mar 4 14:20:00 2026 +0200'
    """
    import time
    sign = 1 if tz_offset_str.startswith('+') else -1
    try:
        hours = int(tz_offset_str[1:3]) # type: ignore
        minutes = int(tz_offset_str[3:5]) # type: ignore
        offset_seconds = sign * (hours * 3600 + minutes * 60) # type: ignore
    except (ValueError, IndexError):
        offset_seconds = 0

    gm = time.gmtime(timestamp + offset_seconds)
    formatted = time.strftime('%a %b %d %H:%M:%S %Y', gm)
    
    # Standardize day format: ' 4' instead of '04' for consistency
    day_str = time.strftime('%d', gm)
    if day_str.startswith('0'):
        formatted = formatted.replace(f" {day_str} ", f"  {day_str[1]} ", 1)

    return f"{formatted} {tz_offset_str}"


# ── Path & Filename Sanitization ─────────────────────────────────────

INVALID_WIN_CHARS = r'[\x00-\x1f\\?*<>|:"]'
RESERVED_WIN_NAMES = {
    "CON", "PRN", "AUX", "NUL", "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9"
}

def sanitize_filename(name: str) -> str:
    """
    Guarantees a safe filename for all filesystems.
    - Replaces \r, \n, \t and control characters with underscores
    - Normalizes Unicode to NFC
    - Replaces Windows-illegal characters with underscores
    - Strips leading/trailing whitespace and trailing dots
    """
    if not name:
        return "unnamed_file"

    # 1. Unicode Normalization (NFC)
    name = unicodedata.normalize('NFC', name)
    
    # 2. Replace all Windows-illegal and control characters (including \r \n \t) with underscores
    name = re.sub(INVALID_WIN_CHARS, '_', name)
    
    # 3. Strip whitespace and basic cleanup
    name = name.strip()
    
    # 4. Final safety check for empty or dot-only names
    name = name.rstrip('. ')
    if not name:
        return "sanitized_file"
        
    return name


# ── CLI Utilities (DEPRECATED: Use deep.utils.ux instead) ───────────────────────────
# Note: Classes have been moved to deep.utils.ux for better consolidation.
