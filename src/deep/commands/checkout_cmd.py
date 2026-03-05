"""
deep.commands.checkout_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep checkout <target>`` command implementation.

Supports checking out a branch name or a commit SHA.  Safety checks prevent
data loss by aborting if there are uncommitted local changes.
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


from concurrent.futures import ThreadPoolExecutor

def _clear_tracked_files(repo_root: Path, index: Index) -> None:
    """Remove all files that are currently tracked in the index (parallel)."""
    def unlink_worker(rel_path: str):
        full = repo_root / rel_path
        if full.exists():
            full.unlink()
    
    if index.entries:
        max_workers = min(os.cpu_count() or 4, len(index.entries))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            executor.map(unlink_worker, index.entries.keys())
    
    # Cleanup empty dirs (sequential is fine, it's fast)
    for rel_path in index.entries:
        full = repo_root / rel_path
        parent = full.parent
        while parent != repo_root:
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent


def _collect_restore_tasks(
    objects_dir: Path,
    tree: Tree,
    prefix: str = "",
) -> list[tuple[str, str, bool]]:
    """Recursively collect (rel_path, blob_sha, is_missing) for restoration."""
    tasks = []
    for entry in tree.entries:
        rel_path = f"{prefix}/{entry.name}" if prefix else entry.name
        try:
            obj = read_object(objects_dir, entry.sha)
            if isinstance(obj, Blob):
                tasks.append((rel_path, entry.sha, False))
            elif isinstance(obj, Tree):
                tasks.extend(_collect_restore_tasks(objects_dir, obj, prefix=rel_path))
        except FileNotFoundError:
            # Partial clone: object missing if filtered. Assume blob.
            tasks.append((rel_path, entry.sha, True))
    return tasks


def _restore_worker(repo_root: Path, objects_dir: Path, rel_path: str, sha: str, is_missing: bool) -> tuple[str, str, int, float]:
    """Write a single file and return its index entry data."""
    if is_missing:
        # For partial clones, we don't have the blob, so we can't write it.
        # Record into index with size 0 and mtime 0.
        return rel_path, sha, 0, 0.0

    obj = read_object(objects_dir, sha)
    file_path = repo_root / rel_path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(obj.serialize_content())
    stat = file_path.stat()
    return rel_path, sha, stat.st_size, stat.st_mtime


def _restore_tree_parallel(
    repo_root: Path,
    objects_dir: Path,
    tree: Tree,
    new_index: Index,
) -> None:
    """Restore the whole tree using a thread pool."""
    tasks = _collect_restore_tasks(objects_dir, tree)
    if not tasks:
        return

    max_workers = min(os.cpu_count() or 4, len(tasks))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(_restore_worker, repo_root, objects_dir, path, sha, missing) for path, sha, missing in tasks]
        for f in futures:
            rel_path, sha, size, mtime = f.result()
            new_index.entries[rel_path] = IndexEntry(sha=sha, size=size, mtime=mtime)


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
    if not getattr(args, "force", False) and _has_uncommitted_changes(repo_root):
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
    _restore_tree_parallel(repo_root, objects_dir, tree_obj, new_index)

    # 3. Write the new index.
    write_index(dg_dir, new_index)

    # 4. Update HEAD.
    update_head(dg_dir, new_head)

    if branch_sha is not None:
        print(f"Switched to branch '{target}'")
    else:
        print(f"HEAD is now at {commit_sha[:7]}")
