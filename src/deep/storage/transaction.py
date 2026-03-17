"""
deep.storage.transaction
~~~~~~~~~~~~~~~~~~~~~~~~

Atomic transaction manager for repository operations.
"""

from __future__ import annotations
import logging
from pathlib import Path
from typing import Optional, List, Any

from deep.storage.txlog import TransactionLog
from deep.core.locks import RepositoryLock, BranchLock, IndexLock
from deep.core.errors import TransactionError, LockError

logger = logging.getLogger("deep.storage.transaction")

class TransactionManager:
    """Context manager for atomic repository operations.
    
    Handles:
    1. Acquisition of required locks (Repository, Index, Branch).
    2. Initialization of WAL (TransactionLog).
    3. Automatic rollback on exception or commit on success.
    """

    def __init__(self, dg_dir: Path, 
                 branch_name: Optional[str] = None, 
                 use_index_lock: bool = True,
                 use_repo_lock: bool = True,
                 timeout: float = 10.0):
        self.dg_dir = dg_dir
        self.branch_name = branch_name
        self.use_index_lock = use_index_lock
        self.use_repo_lock = use_repo_lock
        self.timeout = timeout
        
        self.txlog = TransactionLog(dg_dir)
        self.locks: List[Any] = []
        self._tx_id: Optional[str] = None

    def __enter__(self) -> 'TransactionManager':
        try:
            # 1. Acquire Locks in hierarchical order: Repo -> Branch -> Index
            if self.use_repo_lock:
                repo_lock = RepositoryLock(self.dg_dir, timeout=self.timeout)
                repo_lock.acquire()
                self.locks.append(repo_lock)
            
            if self.branch_name:
                branch_lock = BranchLock(self.dg_dir, self.branch_name, timeout=self.timeout)
                branch_lock.acquire()
                self.locks.append(branch_lock)
                
            if self.use_index_lock:
                index_lock = IndexLock(self.dg_dir, timeout=self.timeout)
                index_lock.acquire()
                self.locks.append(index_lock)
        except TimeoutError as e:
            self._cleanup_locks()
            raise LockError(f"Failed to acquire locks for transaction: {e}")

        return self

    def begin(self, operation: str, details: str = "", 
              target_object_id: str = "", branch_ref: str = "", 
              previous_commit_sha: str = ""):
        """Initialize the WAL log entry."""
        if self._tx_id:
            raise TransactionError("Transaction already begun")
        
        try:
            self._tx_id = self.txlog.begin(
                operation=operation,
                details=details,
                target_object_id=target_object_id,
                branch_ref=branch_ref,
                previous_commit_sha=previous_commit_sha
            )
            logger.debug(f"Transaction begun: {self._tx_id} ({operation})")
        except Exception as e:
            self._cleanup_locks()
            raise TransactionError(f"WAL initialization failed: {e}")
        return self._tx_id

    def commit(self):
        """Finalize the transaction."""
        if not self._tx_id:
            raise TransactionError("No transaction in progress")
        
        try:
            self.txlog.commit(self._tx_id)
            logger.debug(f"Transaction committed: {self._tx_id}")
            self._tx_id = None
        except Exception as e:
            raise TransactionError(f"Transaction commit failed: {e}")

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._tx_id:
            import os
            # If we are in a simulated crash test, do NOT write a ROLLBACK record.
            # This allows the recovery system to find the incomplete transaction and recover.
            if os.environ.get("DEEP_CRASH_TEST"):
                logger.warning(f"Simulated crash detected, leaving transaction {self._tx_id} incomplete for recovery.")
            else:
                logger.warning(f"Aborting incomplete transaction: {self._tx_id}")
                try:
                    self.txlog.rollback(self._tx_id, str(exc_val) if exc_val else "Success/Manual exit without commit")
                except Exception as e:
                    logger.error(f"Failed to rollback transaction {self._tx_id}: {e}")
        
        self._cleanup_locks()

    def _cleanup_locks(self):
        # Release locks in reverse order
        while self.locks:
            lock = self.locks.pop()
            try:
                lock.release()
            except Exception as e:
                logger.error(f"Failed to release lock {lock}: {e}")
