"""
deep.commands.reset_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep reset [--hard] <commit>`` command implementation.

Moves HEAD (and the current branch) to the specified commit.
With ``--hard``, also resets the index and working directory.
"""

from __future__ import annotations

import sys
from pathlib import Path

from deep.storage.index import Index, IndexEntry, read_index, write_index
from deep.storage.objects import Blob, Commit, Tree, read_object
from deep.core.refs import get_current_branch, update_branch, update_head, resolve_revision
from deep.core.repository import DEEP_GIT_DIR, find_repo


def run(args) -> None:  # type: ignore[no-untyped-def]
    """Execute the ``reset`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    dg_dir = repo_root / DEEP_GIT_DIR
    objects_dir = dg_dir / "objects"
    raw_target: str = args.commit
    target_sha: str = resolve_revision(dg_dir, raw_target)
    
    if not target_sha:
        print(f"Error: commit '{raw_target}' does not exist.", file=sys.stderr)
        sys.exit(1)

    # Validate target.
    try:
        obj = read_object(objects_dir, target_sha)
    except FileNotFoundError:
        print(f"Error: commit '{target_sha}' does not exist.", file=sys.stderr)
        sys.exit(1)

    if not isinstance(obj, Commit):
        print(f"Error: '{target_sha}' is not a commit.", file=sys.stderr)
        sys.exit(1)

    # Move branch pointer (or HEAD if detached).
    branch = get_current_branch(dg_dir)
    if branch:
        update_branch(dg_dir, branch, target_sha)
    else:
        update_head(dg_dir, target_sha)

    if args.hard:
        # Reset index and working directory.
        tree = read_object(objects_dir, obj.tree_sha)
        if not isinstance(tree, Tree):
            print("Error: could not read tree.", file=sys.stderr)
            sys.exit(1)

        # Clear tracked files.
        current_index = read_index(dg_dir)
        for rel_path in current_index.entries:
            full = repo_root / rel_path
            if full.exists():
                full.unlink()

        # Restore tree.
        new_index = Index()
        for entry in tree.entries:
            blob = read_object(objects_dir, entry.sha)
            if isinstance(blob, Blob):
                file_path = repo_root / entry.name
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_bytes(blob.data)
                stat = file_path.stat()
                new_index.entries[entry.name] = IndexEntry(
                    sha=entry.sha,
                    size=stat.st_size,
                    mtime=stat.st_mtime,
                )
        write_index(dg_dir, new_index)
        print(f"HEAD is now at {target_sha[:7]} (hard reset)")
    else:
        print(f"HEAD is now at {target_sha[:7]} (soft reset)")
