"""
deep.commands.rebase_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep rebase <branch>`` command implementation.
"""

from __future__ import annotations

import sys
from pathlib import Path

from deep.commands.merge_cmd import _restore_tree_to_workdir
from deep.storage.index import DeepIndex, DeepIndexEntry, read_index, write_index
from deep.core.merge import find_lca, three_way_merge
from deep.storage.objects import Commit, Tree, read_object
from deep.core.refs import (
    get_branch,
    get_current_branch,
    resolve_head,
    update_branch,
    update_head,
)
from deep.core.repository import DEEP_DIR, find_repo
from deep.core.reconcile import logical_rebase

def run(args) -> None:  # type: ignore[no-untyped-def]
    """Execute the ``rebase`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"DeepGit: error: {exc}", file=sys.stderr)
        sys.exit(1)

    dg_dir = repo_root / DEEP_DIR
    objects_dir = dg_dir / "objects"
    target_branch = args.branch

    # Resolve head and target branch
    head_sha = resolve_head(dg_dir)
    if not head_sha:
        print("DeepGit: error: no commits on current branch.", file=sys.stderr)
        sys.exit(1)

    target_sha = get_branch(dg_dir, target_branch)
    if not target_sha:
        # Try resolving as SHA directly
        target_sha = target_branch if len(target_branch) == 40 else ""
        if not target_sha:
            print(f"DeepGit: error: branch or SHA '{target_branch}' not found.", file=sys.stderr)
            sys.exit(1)

    if head_sha == target_sha:
        print("Current branch is up to date.")
        return

    from deep.core.status import compute_status
    status = compute_status(repo_root)
    if status.staged_new or status.staged_modified or status.staged_deleted or status.modified or status.deleted:
        print("DeepGit: error: working directory not clean.", file=sys.stderr)
        sys.exit(1)

    try:
        from deep.core.merge import find_lca
        lca = find_lca(objects_dir, head_sha, target_sha)
        
        if head_sha == target_sha or lca == target_sha:
            print("Current branch is up to date.")
            return

        # Fast-forward check
        if lca == head_sha:
            new_head, renamed_log = target_sha, {}
            print(f"Fast-forwarded to {target_branch}.")
        else:
            new_head, renamed_log = logical_rebase(repo_root, objects_dir, head_sha, target_sha)
            if renamed_log:
                print("Windows Path Sanitization applied.")
    except RuntimeError as e:
        print(f"Rebase aborted: {e}", file=sys.stderr)
        sys.exit(1)

    # Update branch pointer and checkout
    curr_branch = get_current_branch(dg_dir)
    if curr_branch:
        update_branch(dg_dir, curr_branch, new_head)
    else:
        update_head(dg_dir, new_head)
        
    # Restore working directory
    target_commit = read_object(objects_dir, new_head)
    assert isinstance(target_commit, Commit)
    tree = read_object(objects_dir, target_commit.tree_sha)
    assert isinstance(tree, Tree)
    
    # Clean up old files from index to avoid stale entries
    old_index = read_index(dg_dir)
    for rel_path in old_index.entries:
        full = repo_root / rel_path
        if full.exists() and full.is_file():
            try:
                full.unlink()
            except OSError:
                pass

    new_index = DeepIndex()
    _restore_tree_to_workdir(repo_root, objects_dir, tree, new_index)
    write_index(dg_dir, new_index)
    
    if lca != head_sha:
        print(f"DeepGit: Successfully rebased and updated {curr_branch or 'HEAD'}.")
