"""
deep.core.state
~~~~~~~~~~~~~~~~~~~~~~
Repository state validation engine.
"""

from __future__ import annotations
from pathlib import Path
from deep.core.constants import DEEP_DIR # type: ignore
import os
import sys
from deep.core.status import compute_status # type: ignore
from deep.core.git_compat import get_git_tracked_files, is_git_managed # type: ignore
from deep.utils.logger import get_logger

logger = get_logger("deep.core.state")

def validate_repo_state(repo_root: Path) -> None:
    """Validate that the repository has no uncommitted changes (index/worktree).
    
    This is used after operations like merges to ensure state consistency.
    """
    status = compute_status(repo_root)
    
    # We consider the state "corrupted" if there are staged changes 
    # that weren't expected or modifications that make the merge dirty.
    if status.staged_new or status.staged_modified or status.staged_deleted:
        raise Exception("Repository state invalid: unexpected staged changes.")
        
    # Get Git-managed files to exclude them from the dirty check
    git_tracked = get_git_tracked_files(repo_root)
    
    dirty_modified = [m for m in status.modified if not is_git_managed(repo_root, m, git_tracked)]
    dirty_deleted = [d for d in status.deleted if not is_git_managed(repo_root, d, git_tracked)]

    if dirty_modified or dirty_deleted:
        logger.debug(f"Dirty modified: {dirty_modified}")
        logger.debug(f"Dirty deleted: {dirty_deleted}")
            
        raise Exception("Repository state invalid: dirty working directory (modified/deleted files).")
