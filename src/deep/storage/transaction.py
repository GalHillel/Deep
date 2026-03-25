"""
deep.storage.transaction
~~~~~~~~~~~~~~~~~~~~~~~~

Atomic transaction manager for repository operations.
"""

from __future__ import annotations
import os
import time
import logging
from pathlib import Path
from typing import Optional, List, Any, Tuple

from deep.storage.txlog import TransactionLog
from deep.storage.cache import CacheManager
from deep.core.locks import RepositoryLock, BranchLock, IndexLock, BaseLock
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
                 timeout: float = 20.0):
        self.dg_dir = dg_dir
        self.branch_name = branch_name
        self.use_index_lock = use_index_lock
        self.use_repo_lock = use_repo_lock
        self.timeout = timeout
        
        self.txlog = TransactionLog(dg_dir)
        self.locks: List[Any] = []
        self._tx_id: Optional[str] = None
        self._backup_path: Optional[Path] = None
        self._index_existed_at_start: bool = False

    def __enter__(self) -> 'TransactionManager':
        try:
            # 1. Acquire Locks in hierarchical order: Repo -> Branch -> Index
            if self.use_repo_lock:
                repo_lock = RepositoryLock(self.dg_dir, timeout=self.timeout)
                repo_lock.acquire()
                self.locks.append(repo_lock)
                
                # After acquiring the repo lock, it's safe to handle any crash recovery
                from deep.storage.recovery import recover_stale_index_backups
                recover_stale_index_backups(self.dg_dir)
            
            if self.branch_name:
                branch_lock = BranchLock(self.dg_dir, self.branch_name, timeout=self.timeout)
                branch_lock.acquire()
                self.locks.append(branch_lock)
                
            if self.use_index_lock:
                index_lock = IndexLock(self.dg_dir, timeout=self.timeout)
                index_lock.acquire()
                self.locks.append(index_lock)
        except (TimeoutError, Exception) as e:
            self._cleanup_locks()
            if isinstance(e, TimeoutError):
                raise LockError(f"Failed to acquire locks for transaction: {e}")
            raise

        return self

    def begin(self, operation: str, details: str = "", 
              target_object_id: str = "", branch_ref: str = "", 
              previous_commit_sha: str = ""):
        """Initialize the WAL log entry and create pre-transaction backups."""
        if self._tx_id:
            raise TransactionError("Transaction already begun")
        
        try:
            # Create pre-transaction backup of critical files (Undo-Log pattern)
            index_path = self.dg_dir / "index"
            self._index_existed_at_start = index_path.exists()
            rand = f"{int(time.time())}_{os.getpid()}"
            if self._index_existed_at_start:
                self._backup_path = self.dg_dir / f"index.backup_tx_{rand}"
                import shutil
                # Robust retry for backup (Windows sharing violations)
                max_retries = 20
                for i in range(max_retries):
                    try:
                        shutil.copy2(index_path, self._backup_path)
                        break
                    except OSError:
                        if i == max_retries - 1:
                            raise
                        time.sleep(0.01 * (i + 1))
            else:
                # MARKER: Index didn't exist. If we crash, recovery should delete any partial index.
                self._backup_path = self.dg_dir / f"index.backup_tx_{rand}.new"
                self._backup_path.touch()
            
            self._tx_id = self.txlog.begin(
                operation=operation,
                details=details,
                target_object_id=target_object_id,
                branch_ref=branch_ref,
                previous_commit_sha=previous_commit_sha
            )
            logger.debug(f"Transaction begun: {self._tx_id} ({operation})")
        except Exception as e:
            if self._backup_path and self._backup_path.exists():
                try: self._backup_path.unlink()
                except OSError: pass
            self._cleanup_locks()
            raise TransactionError(f"WAL initialization failed: {e}")
        return self._tx_id

    def commit(self):
        """Finalize the transaction and clear backups."""
        if not self._tx_id:
            raise TransactionError("No transaction in progress")
        
        try:
            # Ensure index is durable before removing backup
            from deep.storage.index import read_index, write_index
            index = read_index(self.dg_dir)
            write_index(self.dg_dir, index) # This performs fsync & replace
            
            # Phase 16.6: Transactional Cache Invalidation (Disk)
            # Must occur BEFORE WAL commit to ensure consistency on crash.
            try:
                CacheManager(self.dg_dir).invalidate_all()
            except Exception as e:
                logger.warning(f"Disk cache invalidation failed: {e}")
            
            # Phase 16.6: RAM Cache Invalidation (LRU)
            # Critical for preventing stale reads in long-running processes (Web Dashboard).
            from deep.storage.objects import read_object
            try:
                read_object.cache_clear()
            except Exception as e:
                logger.warning(f"RAM cache clear failed: {e}")

            self.txlog.commit(self._tx_id)
            logger.debug(f"Transaction committed: {self._tx_id}")
            self._tx_id = None
            
            # Remove backup on success
            if self._backup_path and self._backup_path.exists():
                try: self._backup_path.unlink()
                except OSError: pass
                self._backup_path = None
        except Exception as e:
            raise TransactionError(f"Transaction commit failed: {e}")

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._tx_id:
            import os
            # If we are in a simulated crash test, do NOT write a ROLLBACK record.
            if os.environ.get("DEEP_CRASH_TEST"):
                logger.warning(f"Simulated crash detected, leaving transaction {self._tx_id} incomplete for recovery.")
            else:
                logger.warning(f"Aborting incomplete transaction: {self._tx_id}")
                try:
                    try:
                        self.txlog.rollback(self._tx_id, str(exc_val) if exc_val else "Success/Manual exit without commit")
                    finally:
                        # Restore from backup on rollback (CRITICAL: Always do this)
                        self._restore_backup()
                except Exception as e:
                    logger.error(f"Failed to rollback transaction {self._tx_id}: {e}")
        
        self._cleanup_locks()

    def _restore_backup(self):
        """Restore the index from backup atomically or remove it if it was new."""
        index_path = self.dg_dir / "index"
        
        if self._backup_path and self._backup_path.exists():
            max_retries = 20
            for i in range(max_retries):
                try:
                    os.replace(self._backup_path, index_path)
                    self._backup_path = None
                    return
                except OSError:
                    if i == max_retries - 1:
                        logger.error(f"Failed to restore backup {self._backup_path} after max retries")
                    time.sleep(0.02 * (i + 1))
            self._backup_path = None
        elif not self._index_existed_at_start:
            # Index was created during transaction, delete it on rollback
            if index_path.exists():
                try:
                    os.remove(index_path)
                except OSError: pass

    def _recover_stale_backups(self):
        """Deprecated: Use recovery.recover_stale_index_backups instead."""
        from deep.storage.recovery import recover_stale_index_backups
        recover_stale_index_backups(self.dg_dir)

    def _cleanup_locks(self):
        # Release locks in reverse order
        while self.locks:
            lock = self.locks.pop()
            try:
                lock.release()
            except Exception as e:
                logger.error(f"Failed to release lock {lock}: {e}")
