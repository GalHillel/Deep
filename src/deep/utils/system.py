"""
deep.utils.system
~~~~~~~~~~~~~~~~~

System-level utilities for robust file and directory operations.
"""

import os
import shutil
import time
import logging
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger("deep.utils.system")

def safe_rmtree(path: Path | str, retries: int = 5, delay: float = 0.2, ignore_errors: bool = False):
    """Robustly remove a directory tree, handling Windows file locking (WinError 32)."""
    path = Path(path)
    if not path.exists():
        return

    def on_error(func: Callable, p: str, exc_info: Exception):
        # Already deleted or not found
        if isinstance(exc_info, FileNotFoundError):
            return
            
        # Handle PermissionError / Access Denied (often WinError 32)
        if isinstance(exc_info, PermissionError):
            # Try to reset permissions in case it's read-only
            try:
                os.chmod(p, 0o777)
                func(p)
                return
            except Exception:
                pass
        
        # If we reach here, we couldn't handle it immediately
        raise exc_info

    for i in range(retries):
        try:
            shutil.rmtree(path, onexc=on_error)
            return
        except (PermissionError, OSError) as e:
            if i == retries - 1:
                if ignore_errors:
                    logger.warning(f"Failed to remove {path} after {retries} attempts: {e}")
                    return
                raise
            time.sleep(delay * (i + 1))


def make_directory_hidden(path: Path) -> None:
    """Make a directory hidden on Windows (no-op on Unix/macOS)."""
    if os.name == 'nt':
        try:
            import ctypes
            # FILE_ATTRIBUTE_HIDDEN = 0x02
            ret = ctypes.windll.kernel32.SetFileAttributesW(str(path.resolve()), 0x02)
            if not ret:
                logger.debug(f"Failed to set hidden attribute on {path}")
        except Exception as e:
            logger.debug(f"Failed to hide {path}: {e}")
