"""
deep.commands.rebase_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep rebase <branch>`` command implementation.
"""

from __future__ import annotations
from deep.core.errors import DeepCLIException

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
from deep.core.constants import DEEP_DIR
from deep.core.repository import find_repo
from deep.core.reconcile import logical_rebase
from deep.storage.transaction import TransactionManager

def run(args) -> None:  # type: ignore[no-untyped-def]
    """Execute the ``rebase`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Deep: error: {exc}", file=sys.stderr)
        raise DeepCLIException(1)

    dg_dir = repo_root / DEEP_DIR
    objects_dir = dg_dir / "objects"
    
    if getattr(args, "interactive", False):
        print("Interactive rebase (-i) is currently not supported in this version.")
        return

    if getattr(args, "continue_rebase", False):
        # In the current atomic logical_rebase model, there is no intermediate state to continue.
        # If the rebase was successful, everything is done. If it failed, it rolled back.
        print("No rebase in progress to continue (current rebase model is atomic).")
        return

    if getattr(args, "abort", False):
        from deep.storage.txlog import TransactionLog
        txlog = TransactionLog(dg_dir)
        
        # Check if there's an incomplete rebase transaction (simulating "in-progress")
        incomplete = txlog.get_incomplete()
        rebase_tx = [r for r in incomplete if r.operation == "rebase"]
        
        if rebase_tx:
            # We found a crashed/incomplete rebase. Abort it.
            if txlog.rollback(rebase_tx[0].tx_id, "User requested rebase abort"):
                print("Rebase aborted and state restored.")
            else:
                print("Deep: error: could not abort the active rebase.", file=sys.stderr)
                raise DeepCLIException(1)
        else:
            print("No active rebase to abort.")
        return

    target_branch = args.branch
    if target_branch is None:
        print("Deep: error: the following arguments are required: branch (when not using --continue/--abort)", file=sys.stderr)
        raise DeepCLIException(1)

    # 1. Resolve current HEAD.
    head_sha = resolve_head(dg_dir)
    if head_sha is None:
        print("Deep: error: no commits on current branch.", file=sys.stderr)
        raise DeepCLIException(1)

    # 2. Resolve target branch.
    from deep.core.refs import resolve_revision
    target_sha = resolve_revision(dg_dir, target_branch)
    if target_sha is None:
        print(f"Deep: error: revision '{target_branch}' not found.", file=sys.stderr)
        raise DeepCLIException(1)

    if head_sha == target_sha:
        print("Current branch is up to date.")
        return

    from deep.core.status import compute_status
    status = compute_status(repo_root)
    if status.staged_new or status.staged_modified or status.staged_deleted or status.modified or status.deleted:
        print("Deep: error: working directory not clean.", file=sys.stderr)
        raise DeepCLIException(1)

    with TransactionManager(dg_dir) as tm:
        try:
            from deep.core.merge import find_lca
            lca = find_lca(objects_dir, head_sha, target_sha)
            
            if head_sha == target_sha or lca == target_sha:
                print("Current branch is up to date.")
                return

            # Rebase operation starts.
            curr_branch = get_current_branch(dg_dir)
            
            tm.begin(
                operation="rebase",
                details=f"rebase onto {target_branch}",
                target_object_id=target_sha, # This will be updated by logical_rebase results
                branch_ref=f"refs/heads/{curr_branch}" if curr_branch else "HEAD",
                previous_commit_sha=head_sha,
            )

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
            raise DeepCLIException(1)

        # Update branch pointer and checkout
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
        from deep.storage.index import read_index_no_lock, write_index_no_lock
        old_index = read_index_no_lock(dg_dir)
        for rel_path in old_index.entries:
            full = repo_root / rel_path
            if full.exists() and full.is_file():
                try:
                    full.unlink()
                except OSError:
                    pass

        new_index = DeepIndex()
        _restore_tree_to_workdir(repo_root, objects_dir, tree, new_index)
        write_index_no_lock(dg_dir, new_index)
        
        tm.commit()
    
    if lca != head_sha:
        print(f"Deep: Successfully rebased and updated {curr_branch or 'HEAD'}.")
