"""
deep_git.core.utils
~~~~~~~~~~~~~~~~~~~~
Foundational utilities for Deep Git: content hashing and atomic file writes.

Every write in this project goes through :class:`AtomicWriter` to guarantee
crash-safety — data is written to a temporary file and then atomically
renamed via :func:`os.replace`.
"""

from __future__ import annotations

import hashlib
import os
import sys
import tempfile
from pathlib import Path
from typing import Optional, Union


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

    # ------------------------------------------------------------------
    # Context-manager protocol
    # ------------------------------------------------------------------

    def __enter__(self) -> "AtomicWriter":
        self.target.parent.mkdir(parents=True, exist_ok=True)
        # Create temp file in the SAME directory so os.replace is guaranteed
        # to be atomic on all platforms (same filesystem).
        fd, tmp_name = tempfile.mkstemp(
            dir=str(self.target.parent),
            prefix=".tmp_deep_git_",
        )
        self._fd = fd
        self._tmp_path = Path(tmp_name)
        self._file = os.fdopen(fd, self.mode)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:  # type: ignore[override]
        if exc_type is not None:
            # An error occurred — clean up the temp file.
            self._file.close()  # type: ignore[union-attr]
            try:
                self._tmp_path.unlink()  # type: ignore[union-attr]
            except OSError:
                pass
            return

        # Happy path — flush → fsync → atomic rename.
        self._file.flush()  # type: ignore[union-attr]
        os.fsync(self._file.fileno())  # type: ignore[union-attr]
        self._file.close()  # type: ignore[union-attr]
        os.replace(str(self._tmp_path), str(self.target))

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


# ── CLI Utilities ───────────────────────────────────────────────────

class Color:
    """Helper class for ANSI colors, respects TTY."""
    USE_COLOR = sys.stdout.isatty()

    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"

    @classmethod
    def wrap(cls, color: str, text: str) -> str:
        """Wrap text in color, returning uncolored text if not in a TTY."""
        if cls.USE_COLOR:
            return f"{color}{text}{cls.RESET}"
        return text
