"""
deep.utils.logger
~~~~~~~~~~~~~~~~~

Standardized logging for Deep.
"""

import logging
import os
from pathlib import Path

def setup_logger(name: str, log_file: Optional[Path] = None, level=logging.INFO):
    """Configure and return a logger instance."""
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    )

    # Console handler
    ch = logging.StreamHandler()
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    # File handler
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_file)
        fh.setFormatter(formatter)
        logger.addHandler(fh)

    return logger

# Default repository logger
repo_logger = logging.getLogger("deep")
