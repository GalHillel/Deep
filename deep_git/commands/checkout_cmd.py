"""
deep_git.commands.checkout_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deepgit checkout <target>`` command implementation.

Supports checking out a branch name or a commit SHA.  Safety checks prevent
data loss by aborting if there are uncommitted local changes.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from deep_git.core.index import Index, IndexEntry, read_index, write_index
from deep_git.core.objects import Blob, Commit, Tree, read_object
from deep_git.core.refs import (
    get_branch,
    get_current_branch,
    resolve_head,
    update_head,
)
from deep_git.core.repository import DEEP_GIT_DIR, find_repo
from deep_git.core.status import compute_status


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


def _clear_tracked_files(repo_root: Path, index: Index) -> None:
    """Remove all files that are currently tracked in the index."""
    for rel_path in index.entries:
        full = repo_root / rel_path
        if full.exists():
            full.unlink()
        # Remove empty parent dirs (bottom-up).
        parent = full.parent
        while parent != repo_root:
            try:
                parent.rmdir()  # only removes if empty
            except OSError:
                break
            parent = parent.parent


def _restore_tree(
    repo_root: Path,
    objects_dir: Path,
    tree: Tree,
    new_index: Index,
) -> None:
    """Restore files from a Tree's blobs into the working directory.

    Also populates *new_index* with the restored entries.
    """
    for entry in tree.entries:
        obj = read_object(objects_dir, entry.sha)
        if isinstance(obj, Blob):
            file_path = repo_root / entry.name
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_bytes(obj.data)
            stat = file_path.stat()
            new_index.entries[entry.name] = IndexEntry(
                sha=entry.sha,
                size=stat.st_size,
                mtime=stat.st_mtime,
            )


def run(args) -> None:  # type: ignore[no-untyped-def]
    """Execute the ``checkout`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    dg_dir = repo_root / DEEP_GIT_DIR
    objects_dir = dg_dir / "objects"
    target = args.target

    # Safety check.
    if _has_uncommitted_changes(repo_root):
        print(
            "Error: your local changes would be overwritten by checkout.\n"
            "Please commit or stash your changes before switching.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Resolve target — branch name or commit SHA.
    branch_sha = get_branch(dg_dir, target)
    if branch_sha is not None:
        # Checking out a branch.
        commit_sha = branch_sha
        new_head = f"ref: refs/heads/{target}"
    elif len(target) == 40:
        # Detached HEAD — raw SHA.
        commit_sha = target
        new_head = commit_sha
    else:
        print(f"Error: '{target}' is not a branch or a valid commit SHA.", file=sys.stderr)
        sys.exit(1)

    # Read the target commit's tree.
    commit_obj = read_object(objects_dir, commit_sha)
    if not isinstance(commit_obj, Commit):
        print(f"Error: {commit_sha} is not a commit.", file=sys.stderr)
        sys.exit(1)

    tree_obj = read_object(objects_dir, commit_obj.tree_sha)
    if not isinstance(tree_obj, Tree):
        print(f"Error: could not read tree for commit {commit_sha}.", file=sys.stderr)
        sys.exit(1)

    # 1. Clear tracked files.
    current_index = read_index(dg_dir)
    _clear_tracked_files(repo_root, current_index)

    # 2. Restore the target tree.
    new_index = Index()
    _restore_tree(repo_root, objects_dir, tree_obj, new_index)

    # 3. Write the new index.
    write_index(dg_dir, new_index)

    # 4. Update HEAD.
    update_head(dg_dir, new_head)

    if branch_sha is not None:
        print(f"Switched to branch '{target}'")
    else:
        print(f"HEAD is now at {commit_sha[:7]}")
