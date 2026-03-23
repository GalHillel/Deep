import os
import re
import time
import logging
from pathlib import Path
from typing import Optional
from deep.core.locks import _is_process_alive, BaseLock

logger = logging.getLogger("deep.storage.recovery")

def recover_stale_index_backups(dg_dir: Path):
    """Identify and restore any stale backups and locks from dead processes."""
    
    # 1. Recover stale index backups (Undo-Log)
    backups = list(dg_dir.glob("index.backup_tx_*"))
    for p in backups:
        match = re.search(r"backup_tx_\d+_(\d+)", p.name)
        if match:
            try:
                pid = int(match.group(1))
                if not _is_process_alive(pid):
                    if p.name.endswith(".new"):
                        # Index was newly created, delete it
                        index_path = dg_dir / "index"
                        if index_path.exists():
                            try: os.remove(index_path)
                            except OSError: pass
                        try: p.unlink()
                        except OSError: pass
                    else:
                        # Restore from backup
                        max_retries = 10
                        for i in range(max_retries):
                            try:
                                os.replace(p, dg_dir / "index")
                                break
                            except OSError:
                                if i == max_retries - 1: p.unlink()
                                time.sleep(0.01)
            except (ValueError, OSError):
                try: p.unlink()
                except OSError: pass
    
    # 2. Aggressive stale lock cleanup (repo.lock, indexed.lock, txlog.lock, etc.)
    for p in list(dg_dir.glob("*.lock")):
        try:
            lock = BaseLock(p)
            owner_pid = lock._get_lock_pid()
            if owner_pid is not None and not _is_process_alive(owner_pid):
                logger.debug(f"Cleaning leaked stale lock: {p.name}")
                try: os.remove(p)
                except OSError: pass
        except Exception:
            pass
