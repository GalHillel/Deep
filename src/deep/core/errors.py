"""
deep.core.errors
~~~~~~~~~~~~~~~~

Standardized exception hierarchy for Deep.
"""

class DeepError(Exception):
    """Base class for all Deep errors."""
    def __init__(self, message: str, details: dict = None):
        super().__init__(message)
        self.details = details or {}

class StorageError(DeepError):
    """Raised when an object cannot be read or written."""
    pass

class LockError(DeepError):
    """Raised when a lock cannot be acquired or is violated."""
    pass

class TransactionError(DeepError):
    """Raised when a transaction fails or cannot be started."""
    pass

class ProtocolError(DeepError):
    """Raised when a network protocol violation occurs."""
    pass

class ConfigError(DeepError):
    """Raised when configuration is invalid or missing."""
    pass
