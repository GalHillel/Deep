"""
deep.commands.checkout_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
DeepBridge ``checkout <target>`` command implementation.

Supports checking out a branch name or a commit SHA.  Safety checks prevent
data loss by aborting if there are uncommitted local changes.
Uses WAL-based crash recovery and proper locking.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from deep.storage.index import Index, IndexEntry, read_index, write_index
from deep.storage.objects import Blob, Commit, Tree, read_object
from deep.core.refs import (
    get_branch,
    get_current_branch,
    resolve_head,
    update_head,
)
from deep.core.repository import DEEP_GIT_DIR, find_repo
from deep.core.status import compute_status


def _has_uncommitted_changes(repo_root: Path) -> bool:
    """Return True if there are any staged or unstaged changes."""
    status = compute_status(repo_root)
    return bool(
        status.staged_new
        or status.staged_modified
        or status.staged_deleted
        or status.modified
        or status.deleted
    )


def _get_tree_files(objects_dir: Path, tree_sha: str, prefix: str = "") -> dict[str, str]:
    """Recursively collect all {rel_path: sha} from a tree."""
    from deep.core.reconcile import sanitize_path
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


def run(args) -> None:  # type: ignore[no-untyped_def]
    """Execute the ``checkout`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"DeepBridge: error: {exc}", file=sys.stderr)
        sys.exit(1)

    dg_dir = repo_root / DEEP_GIT_DIR
    objects_dir = dg_dir / "objects"
    target = args.target
    force = getattr(args, "force", False)

    # Handle -b flag: create and switch to a new branch
    new_branch_name = getattr(args, "branch", None)
    if new_branch_name:
        from deep.core.refs import update_branch
        head_sha = resolve_head(dg_dir)
        if not head_sha:
            print("DeepBridge: error: cannot create branch without commits.", file=sys.stderr)
            sys.exit(1)
        update_branch(dg_dir, new_branch_name, head_sha)
        update_head(dg_dir, f"ref: refs/heads/{new_branch_name}")
        print(f"DeepBridge: switched to a new branch '{new_branch_name}'")
        return

    # Resolve target — branch name or commit SHA.
    branch_sha = get_branch(dg_dir, target)
    if branch_sha is not None:
        commit_sha = branch_sha
        new_head = f"ref: refs/heads/{target}"
    elif len(target) == 40:
        commit_sha = target
        new_head = commit_sha
    else:
        # Try resolving as a partial SHA or other revision
        from deep.core.refs import resolve_revision
        commit_sha = resolve_revision(dg_dir, target)
        if not commit_sha:
            print(f"DeepBridge: error: '{target}' is not a branch or a valid commit SHA.", file=sys.stderr)
            sys.exit(1)
        new_head = commit_sha

    # Read the target commit.
    commit_obj = read_object(objects_dir, commit_sha)
    if not isinstance(commit_obj, Commit):
        print(f"DeepBridge: error: {commit_sha} is not a commit.", file=sys.stderr)
        sys.exit(1)

    # 1. Compute state
    current_index = read_index(dg_dir)
    status = compute_status(repo_root)
    target_files = _get_tree_files(objects_dir, commit_obj.tree_sha)

    # 2. Safety check: Protect untracked and modified files
    if not force:
        conflicts = []
        for path in status.untracked:
            if path in target_files:
                conflicts.append(path)
        
        for path in status.modified:
            if path in target_files and path in current_index.entries and target_files[path] != current_index.entries[path].sha:
                conflicts.append(path)

        # Also block if there are staged changes
        if status.staged_new or status.staged_modified or status.staged_deleted:
            print("DeepBridge: error: you have staged changes. Please commit or stash them before switching.", file=sys.stderr)
            sys.exit(1)

        if conflicts:
            print("DeepBridge: error: the following files would be overwritten by checkout:", file=sys.stderr)
            for c in conflicts[:10]:
                print(f"  {c}", file=sys.stderr)
            if len(conflicts) > 10:
                print(f"  ... and {len(conflicts) - 10} more", file=sys.stderr)
            print("Please commit, stash, or remove them before switching.", file=sys.stderr)
            print("Or use --force to overwrite.", file=sys.stderr)
            sys.exit(1)

    # 3. Acquire locks for the checkout operation
    from deep.core.locks import RepositoryLock
    repo_lock = RepositoryLock(dg_dir)
    try:
        repo_lock.acquire()
    except TimeoutError as e:
        print(f"DeepBridge: error: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        # 4. WAL-based transactional checkout
        from deep.storage.txlog import TransactionLog
        txlog = TransactionLog(dg_dir)

        previous_head = resolve_head(dg_dir)
        logical_ref = "HEAD"  # Checkout always updates HEAD

        tx_id = txlog.begin(
            operation="checkout",
            details=f"checkout {target}",
            target_object_id=commit_sha,
            branch_ref=logical_ref,
            previous_commit_sha=previous_head or "",
        )

        # Crash hook: after WAL begin, before working directory changes
        if os.environ.get("DEEP_CRASH_TEST") == "CHECKOUT_BEFORE_WD_UPDATE":
            raise BaseException("DeepBridge: simulated crash before working directory update")

        try:
            # Files to remove: currently tracked but not in target
            to_remove = [p for p in current_index.entries if p not in target_files]
            
            # Apply removals
            for p in to_remove:
                full = repo_root / p
                if full.exists():
                    full.unlink()
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

            # 5. Finalize: Write index and update HEAD atomically
            write_index(dg_dir, new_index)
            update_head(dg_dir, new_head)

            # Crash hook: after HEAD update, before WAL commit
            if os.environ.get("DEEP_CRASH_TEST") == "CHECKOUT_AFTER_HEAD_UPDATE":
                raise BaseException("DeepBridge: simulated crash after HEAD update")

            txlog.commit(tx_id)
        except Exception as e:
            txlog.rollback(tx_id, str(e))
            raise

        if branch_sha is not None:
            print(f"DeepBridge: switched to branch '{target}'")
        else:
            print(f"DeepBridge: HEAD is now at {commit_sha[:7]}")

    finally:
        repo_lock.release()
