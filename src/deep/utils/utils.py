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
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Optional, Union


class DeepError(Exception):
    """Base exception for all DeepBridge errors."""
    pass


def hash_bytes(data: bytes) -> str:
    """Return the hex-encoded SHA-1 hash of *data*.

    SHA-1 is used for compatibility with Git's content-addressable storage
    scheme.  The 40-character lowercase hex digest is returned.

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
        self.mode = mode
        self._fd: Optional[int] = None
        self._tmp_path: Optional[Path] = None
        self._file = None
        self._is_append = "a" in self.mode
        if self._is_append:
            # If appending, we actually open the temp file in write mode
            # because we'll copy existing contents over first.
            self.mode = self.mode.replace("a", "w")

    # ------------------------------------------------------------------
    # Context-manager protocol
    # ------------------------------------------------------------------

    def __enter__(self) -> "AtomicWriter":
        self.target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            dir=str(self.target.parent),
            prefix=".tmp_deep_git_",
        )
        self._fd = fd
        self._tmp_path = Path(tmp_name)

        if self._is_append and self.target.exists():
            with open(self.target, "rb") as src:
                # Copy to the raw FD
                os.write(self._fd, src.read())

        self._file = os.fdopen(self._fd, self.mode)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:  # type: ignore[override]
        if self._file:
            try:
                if exc_type is not None:
                    self._file.close()
                    if self._tmp_path.exists():
                        self._tmp_path.unlink()
                    return

                self._file.flush()
                try:
                    os.fsync(self._file.fileno())
                except OSError:
                    pass # Some systems don't support fsync on all files
                self._file.close()
                self._file = None
                
                os.replace(str(self._tmp_path), str(self.target))
            except Exception:
                if self._file:
                    try: self._file.close()
                    except: pass
                if self._tmp_path and self._tmp_path.exists():
                    try: self._tmp_path.unlink()
                    except: pass
                raise
        
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


def format_git_date(timestamp: int, tz_offset_str: str) -> str:
    """Format a Unix timestamp and tz offset into Git's date string.
    Example: 'Tue Mar 4 14:20:00 2026 +0200'
    """
    import time
    sign = 1 if tz_offset_str.startswith('+') else -1
    try:
        hours = int(tz_offset_str[1:3])
        minutes = int(tz_offset_str[3:5])
        offset_seconds = sign * (hours * 3600 + minutes * 60)
    except (ValueError, IndexError):
        offset_seconds = 0

    gm = time.gmtime(timestamp + offset_seconds)
    # Note: %d is zero-padded on Windows, but %e is space-padded.
    # Python on Windows doesn't universally support %e, so we stick to %d
    # but strip leading zero if needed or just use %d.
    formatted = time.strftime('%a %b %d %H:%M:%S %Y', gm)
    
    # Strip leading zero from day for Git compatibility: ' 4' instead of '04'
    # Wait, we can manually replace it:
    # Actually, Git's output looks like 'Tue Mar 4...' or 'Tue Mar 14...'
    day_str = time.strftime('%d', gm)
    if day_str.startswith('0'):
        formatted = formatted.replace(f" {day_str} ", f"  {day_str[1]} ", 1)

    return f"{formatted} {tz_offset_str}"


# ── CLI Utilities (DEPRECATED: Use deep.utils.ux instead) ───────────────────────────
# Note: Classes have been moved to deep.utils.ux for better consolidation.
