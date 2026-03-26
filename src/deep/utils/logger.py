"""
deep.utils.logger
~~~~~~~~~~~~~~~~~

Centralized logging utility for Deep VCS.
Supports togglable console output via DEEP_DEBUG and persistent file logging.
"""

import logging
import os
import sys
from pathlib import Path
from typing import Optional

# Global switch for debug output in console
DEBUG_MODE = os.environ.get("DEEP_DEBUG") == "1"

class DeepLogger:
    """Enhanced logger for Deep with dual-sink (Console/File) support."""
    
    def __init__(self):
        self._loggers = {}
        self._log_file: Optional[Path] = None
        self._file_handler: Optional[logging.FileHandler] = None

    def setup_repo_logging(self, repo_root: Path, is_bare: Optional[bool] = None):
        """Set up file logging to .deep/logs/deep.log or logs/deep.log (bare)."""
        if is_bare is None:
            # Auto-detection: if .deep exists, it's not bare.
            # If objects/ exists but .deep doesn't, it's bare.
            is_bare = not (repo_root / ".deep").is_dir() and (repo_root / "objects").is_dir()
        
        if is_bare:
            log_dir = repo_root / "logs"
        else:
            log_dir = repo_root / ".deep" / "logs"
            
        log_file = log_dir / "deep.log"
        
        if self._log_file == log_file:
            return
            
        # If switching repos, close existing handler first
        if self._file_handler:
            self.shutdown_repo_logging()
            
        try:
            # Special care for bare repos: don't create .deep
            if is_bare or (repo_root / ".deep").is_dir():
                log_dir.mkdir(parents=True, exist_ok=True)
            else:
                # If we are in a non-bare repo but .deep is missing (rare), 
                # we probably shouldn't be logging there yet.
                return
                
            self._log_file = log_file
            
            # Create shared file handler
            formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s')
            self._file_handler = logging.FileHandler(log_file, encoding='utf-8')
            self._file_handler.setFormatter(formatter)
            self._file_handler.setLevel(logging.DEBUG)
            
            # Attach to all existing loggers
            for logger in self._loggers.values():
                logger.addHandler(self._file_handler)
        except Exception:
            # Fallback: ignore logging errors if directory is not writable
            pass

    def shutdown_repo_logging(self):
        """Close and remove the file handler to release file locks."""
        if self._file_handler:
            self._file_handler.close()
            for logger in self._loggers.values():
                logger.removeHandler(self._file_handler)
            self._file_handler = None
            self._log_file = None

    def get_logger(self, name: str) -> logging.Logger:
        """Return a named logger configured for Deep."""
        if name in self._loggers:
            return self._loggers[name]
            
        logger = logging.getLogger(name)
        logger.setLevel(logging.DEBUG) # Internal level is always high; sinks control filtering
        
        # Avoid duplicate handlers if re-initialized
        if not logger.handlers:
            # Console Handler
            ch = logging.StreamHandler(sys.stderr)
            formatter = logging.Formatter('%(message)s') # Default console format is clean
            
            if DEBUG_MODE:
                ch.setLevel(logging.DEBUG)
                # Richer format for debug mode
                formatter = logging.Formatter('[%(name)s] %(levelname)s: %(message)s')
            else:
                ch.setLevel(logging.INFO)
                
            ch.setFormatter(formatter)
            logger.addHandler(ch)
            
            # Attach file handler if already initialized
            if self._file_handler:
                logger.addHandler(self._file_handler)
                
        self._loggers[name] = logger
        return logger

# Global instance
_manager = DeepLogger()

def get_logger(name: str) -> logging.Logger:
    """Access the Deep logging system."""
    return _manager.get_logger(name)

def setup_repo_logging(repo_root: Path, is_bare: Optional[bool] = None):
    """Enable file logging for a specific repository."""
    _manager.setup_repo_logging(repo_root, is_bare)

def shutdown_logging():
    """Release all file logging handles."""
    _manager.shutdown_repo_logging()

# Compatibility: default 'deep' logger
logger = get_logger("deep")
