"""
deep.core.repository
~~~~~~~~~~~~~~~~~~~~

Repository initialization, discovery, and path management.

This module handles the creation of the internal ``.deep`` directory structure
and provides utilities to find the repository root from any sub-directory.
The on-disk layout is designed for DeepBridge consistency and performance.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Union

from deep.utils.utils import AtomicWriter

# Canonical repository directory name for DeepBridge.
DEEP_DIR = ".deep"
# Backward-compatible alias used throughout the existing codebase.
DEEP_GIT_DIR = DEEP_DIR


def _deep_git_path(repo_root: Path) -> Path:
    """Return the absolute path to the internal repository directory for a given root."""
    return repo_root / DEEP_GIT_DIR


def init_repo(path: Union[str, Path]) -> Path:
    """Initialize a new DeepBridge repository at the specified path.

    This creates the internal structure required for tracking history:
    - `objects/`: The content-addressable storage.
    - `refs/heads/`: Branch pointers.
    - `HEAD`: Pointer to the current active branch.
    - `index`: Staging area for upcoming commits.

    Args:
        path: Directory path where the repository should be initialized.

    Returns:
        Path: The absolute path to the internal repository directory.
    """
    repo_root = Path(path).resolve()
    dg = _deep_git_path(repo_root)

    # If the internal directory already exists, treat init as idempotent and
    # repair any missing core structures instead of failing.
    if dg.exists():
        if not dg.is_dir():
            raise FileExistsError(f"DeepBridge internal path exists but is not a directory: {dg}")
    else:
        # Create directory tree for a brand-new repository.
        (dg / "objects").mkdir(parents=True, exist_ok=True)
        (dg / "refs" / "heads").mkdir(parents=True, exist_ok=True)

    # Ensure core subdirectories always exist (self-healing for partial setups).
    (dg / "objects").mkdir(parents=True, exist_ok=True)
    (dg / "refs" / "heads").mkdir(parents=True, exist_ok=True)

    # HEAD → default branch is "main" if HEAD is missing or empty.
    head_path = dg / "HEAD"
    head_needs_init = (not head_path.exists()) or not head_path.read_text(encoding="utf-8").strip()
    if head_needs_init:
        with AtomicWriter(head_path, mode="w") as aw:
            aw.write("ref: refs/heads/main\n")

    # Empty index (binary format) if index is missing or zero-length.
    from deep.storage.index import Index
    index_path = dg / "index"
    index_needs_init = (not index_path.exists()) or index_path.stat().st_size == 0
    if index_needs_init:
        with AtomicWriter(index_path, mode="wb") as aw:
            aw.write(Index().to_binary())

    return dg


def find_repo(start: Union[str, Path] | None = None) -> Path:
    """Walk up from *start* (default: cwd) to find an internal DeepBridge directory.

    Args:
        start: Directory to begin the search from.

    Returns:
        Resolved path to the repository root (the parent of the internal directory).
    """
    current = Path(start or Path.cwd()).resolve()
    while True:
        candidate = current / DEEP_GIT_DIR
        if candidate.is_dir():
            return current
        parent = current.parent
        if parent == current:
            raise FileNotFoundError(
                "Not a DeepBridge repository (or any of the parent directories)"
            )
        current = parent


def checkout(repo_root: Path, target: str, create_branch: bool = False, force: bool = False) -> None:
    print(f"DEBUG: checkout({target}) starting")
    from deep.core.locks import RepositoryLock
    import os
    from deep.core.refs import (
        get_branch,
        resolve_head,
        update_head,
        update_branch,
        resolve_revision,
    )
    from deep.core.status import compute_status
    from deep.storage.index import Index, IndexEntry, read_index_no_lock, write_index_no_lock
    from deep.storage.objects import Commit, Tree, read_object
    from deep.utils.utils import DeepError

    dg_dir = repo_root / DEEP_GIT_DIR
    objects_dir = dg_dir / "objects"
    
    # 1. Acquire RepositoryLock
    with RepositoryLock(dg_dir):
        # 2. Validate
        if create_branch:
            if get_branch(dg_dir, target):
                raise DeepError(f"branch already exists: {target}")
            commit_sha = resolve_head(dg_dir)
            if not commit_sha:
                raise DeepError("cannot create branch without commits")
        else:
            # Resolve target — branch name, commit SHA, or revision.
            commit_sha = resolve_revision(dg_dir, target)
            if not commit_sha:
                raise DeepError(f"'{target}' is not a branch or a valid commit SHA")

        # Read the target commit.
        commit_obj = read_object(objects_dir, commit_sha)
        if not isinstance(commit_obj, Commit):
            raise DeepError(f"{commit_sha} is not a commit")

        # 3. Check for dirty working directory (Dirty State Invariant)
        # Use no-lock read because we ALREADY hold RepositoryLock (index.lock)
        current_index = read_index_no_lock(dg_dir)

        if not force:
            status = compute_status(repo_root, index=current_index)
            if status.staged_new or status.staged_modified or status.staged_deleted:
                raise DeepError("you have staged changes. Please commit or stash them before switching.")
            
            # Check for conflict between modified tracked files and target tree
            target_files = _get_tree_files(objects_dir, commit_obj.tree_sha)
            
            conflicts = []
            for path in status.untracked:
                if path in target_files:
                    conflicts.append(path)
            
            for path in status.modified:
                if path in target_files and path in current_index.entries and target_files[path] != current_index.entries[path].sha:
                    conflicts.append(path)
                    
            if conflicts:
                msg = "the following files would be overwritten by checkout:\n"
                msg += "\n".join(f"  {c}" for c in conflicts[:10])
                if len(conflicts) > 10:
                    msg += f"\n  ... and {len(conflicts) - 10} more"
                raise DeepError(msg)

        # 4. WAL-based Transactional Checkout (Crash Recovery)
        from deep.storage.txlog import TransactionLog
        txlog = TransactionLog(dg_dir)
        previous_head = resolve_head(dg_dir)
        
        tx_id = txlog.begin(
            operation="checkout",
            details=f"checkout {target}",
            target_object_id=commit_sha,
            branch_ref="HEAD",
            previous_commit_sha=previous_head or "",
        )

        try:
            # Crash hook: before working directory update
            if os.environ.get("DEEP_CRASH_TEST") == "CHECKOUT_BEFORE_WD_UPDATE":
                raise BaseException("DeepBridge: simulated crash before working directory update")

            # 4. Update Working Directory
            target_files = _get_tree_files(objects_dir, commit_obj.tree_sha)
            
            # Files to remove: currently tracked but not in target
            to_remove = [p for p in current_index.entries if p not in target_files]
            for p in to_remove:
                full = repo_root / p
                if full.exists():
                    full.unlink()
                    # Clean up empty parent directories
                    parent = full.parent
                    while parent != repo_root:
                        try:
                            parent.rmdir()
                        except OSError:
                            break
                        parent = parent.parent

            # Apply updates
            new_index = Index()
            for p, sha in target_files.items():
                full = repo_root / p
                full.parent.mkdir(parents=True, exist_ok=True)
                obj = read_object(objects_dir, sha)
                full.write_bytes(obj.serialize_content())
                stat = full.stat()
                new_index.entries[p] = IndexEntry(sha=sha, size=stat.st_size, mtime=stat.st_mtime)

            # 5. Update Index
            write_index_no_lock(dg_dir, new_index)

            # 6. Atomic HEAD Ref update
            if create_branch:
                update_branch(dg_dir, target, commit_sha)
                update_head(dg_dir, f"ref: refs/heads/{target}")
            else:
                # Check if target is a branch name
                if get_branch(dg_dir, target):
                    update_head(dg_dir, f"ref: refs/heads/{target}")
                else:
                    update_head(dg_dir, commit_sha)

            # Crash hook: after HEAD update, before WAL commit
            if os.environ.get("DEEP_CRASH_TEST") == "CHECKOUT_AFTER_HEAD_UPDATE":
                raise BaseException("DeepBridge: simulated crash after HEAD update")

            txlog.commit(tx_id)
        except Exception as e:
            txlog.rollback(tx_id, str(e))
            raise


def _get_tree_files(objects_dir: Path, tree_sha: str, prefix: str = "") -> dict[str, str]:
    """Recursively collect all {rel_path: sha} from a tree."""
    from deep.core.reconcile import sanitize_path
    from deep.storage.objects import Tree, read_object
    files = {}
    tree = read_object(objects_dir, tree_sha)
    if not isinstance(tree, Tree):
        return {}
    for entry in tree.entries:
        safe_name, _ = sanitize_path(entry.name)
        rel_path = f"{prefix}/{safe_name}" if prefix else safe_name
        if entry.mode == "40000":
            files.update(_get_tree_files(objects_dir, entry.sha, rel_path))
        else:
            files[rel_path] = entry.sha
    return files
