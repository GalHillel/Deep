"""
deep.commands.branch_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Deep ``branch`` command implementation.
"""

from __future__ import annotations
from deep.core.errors import DeepCLIException

import sys
from pathlib import Path

from deep.core.refs import (
    get_current_branch,
    list_branches,
    resolve_head,
    update_branch,
)
from deep.core.constants import DEEP_DIR
from deep.core.repository import find_repo
from deep.utils.ux import Color
from deep.storage.transaction import TransactionManager


def run(args) -> None:  # type: ignore[no-untyped-def]
    """Execute the ``branch`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Deep: error: {exc}", file=sys.stderr)
        raise DeepCLIException(1)

    dg_dir = repo_root / DEEP_DIR

    with TransactionManager(dg_dir) as tm:
        # 1. List branches (Read-only)
        if args.name is None and not getattr(args, "list", False):
            # No tm.begin() here, it's read-only
            current = get_current_branch(dg_dir)
            branches = list_branches(dg_dir)
            if not branches:
                print("No branches yet (make a commit first).")
                return
            for b in branches:
                if b == current:
                    print(Color.wrap(Color.GREEN, f"* {b}"))
                else:
                    print(f"  {b}")
            return

        # 2. Delete branch
        if getattr(args, "delete", False):
            tm.begin("branch_delete")
            from deep.core.refs import delete_branch
            try:
                delete_branch(dg_dir, args.name)
                print(f"Deleted branch '{args.name}'.")
                tm.commit()
            except Exception as e:
                print(f"Deep: error: {e}", file=sys.stderr)
                raise DeepCLIException(1)
            return

        # 3. Rename branch
        if getattr(args, "rename", None):
            tm.begin("branch_rename")
            from deep.core.refs import delete_branch
            old_name = args.rename
            new_name = args.name
            sha = resolve_head(dg_dir) # Default to HEAD if no start_point
            if hasattr(args, "start_point") and args.start_point:
                from deep.core.refs import resolve_revision
                sha = resolve_revision(dg_dir, args.start_point)
            
            # If we are renaming the branch we are currently on, we need special care?
            # Standard deep -m allows renaming current branch.
            # deep.core.refs.delete_branch refuses to delete current branch.
            target_sha = resolve_head(dg_dir) if old_name == get_current_branch(dg_dir) else None
            
            # Get the actual SHA of the old branch
            from deep.core.refs import get_branch
            old_sha = get_branch(dg_dir, old_name)
            if not old_sha:
                print(f"Deep: error: branch '{old_name}' not found.", file=sys.stderr)
                raise DeepCLIException(1)
                
            update_branch(dg_dir, new_name, old_sha)
            
            # If it was current branch, we need to update HEAD to point to the new name
            if old_name == get_current_branch(dg_dir):
                from deep.core.refs import update_head
                update_head(dg_dir, f"ref: refs/heads/{new_name}")
                
            delete_branch(dg_dir, old_name)
            print(f"Renamed branch '{old_name}' to '{new_name}'.")
            tm.commit()
            return

        # 4. Create a new branch.
        tm.begin("branch_create")
        from deep.core.refs import resolve_revision
        start_point = args.start_point if hasattr(args, "start_point") else "HEAD"
        target_sha = resolve_revision(dg_dir, start_point)
        
        if target_sha is None:
            print(f"Deep: error: Not a valid object name: '{start_point}'", file=sys.stderr)
            raise DeepCLIException(1)
            
        update_branch(dg_dir, args.name, target_sha)
        print(f"Created branch '{args.name}' at {target_sha[:7]}")
        tm.commit()
