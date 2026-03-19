"""
deep.core.state
~~~~~~~~~~~~~~~~~~~~~~
Repository state validation engine.
"""

from __future__ import annotations
from pathlib import Path
from deep.core.constants import DEEP_DIR # type: ignore
from deep.core.status import compute_status # type: ignore

def validate_repo_state(repo_root: Path) -> None:
    """Validate that the repository has no uncommitted changes (index/worktree).
    
    This is used after operations like merges to ensure state consistency.
    """
    status = compute_status(repo_root)
    
    # We consider the state "corrupted" if there are staged changes 
    # that weren't expected or modifications that make the merge dirty.
    if status.staged_new or status.staged_modified or status.staged_deleted:
        raise Exception("Repository state invalid: unexpected staged changes.")
        
    if status.modified or status.deleted:
        # In some cases, we might allow modified files if they weren't part of the merge,
        # but for a PR merge validation, we want a clean worktree.
        raise Exception("Repository state invalid: dirty working directory (modified/deleted files).")
