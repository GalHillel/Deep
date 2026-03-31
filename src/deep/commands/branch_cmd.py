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
from deep.utils.ux import DeepHelpFormatter, format_example
from typing import Any


def setup_parser(subparsers: Any) -> None:
    """Set up the 'branch' command parser."""
    p_branch = subparsers.add_parser(
        "branch",
        help="List, create, or delete branches",
        description="Manage the set of branches in your repository.",
        epilog=f"""
Examples:
{format_example("deep branch", "List local branches")}
{format_example("deep branch new-feature", "Create a new branch")}
{format_example("deep branch -d old-feature", "Delete a branch")}
""",
        formatter_class=DeepHelpFormatter,
    )
    p_branch.add_argument("name", nargs="?", help="The name of the branch to create")
    p_branch.add_argument("-d", "--delete", action="store_true", help="Delete the specified branch")
    p_branch.add_argument("-a", "--all", action="store_true", help="List both local and tracked remote branches")
    p_branch.add_argument("-v", "--verbose", action="count", default=0, help="Show more detail (SHA and tracking info)")
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
            from deep.core.config import Config
            config = Config(repo_root)
            
            branches = list_branches(dg_dir)
            if getattr(args, "all", False):
                # Add remote branches
                from deep.core.refs import list_remote_branches
                for remote, b_list in list_remote_branches(dg_dir).items():
                    for b in b_list:
                        branches.append(f"remotes/{remote}/{b}")

            if not branches:
                print("No branches yet (make a commit first).")
                return

            verbose = getattr(args, "verbose", 0)
            if getattr(args, "vv", False):
                verbose = 2
            for b in branches:
                is_remote = b.startswith("remotes/")
                actual_name = b.split("/", 2)[-1] if is_remote else b
                
                prefix = "* " if b == current else "  "
                line = f"{prefix}{b}"
                
                if verbose > 0:
                    from deep.core.refs import get_branch, get_remote_ref
                    if is_remote:
                        parts = b.split("/")
                        sha = get_remote_ref(dg_dir, parts[1], parts[2])
                    else:
                        sha = get_branch(dg_dir, b)
                    
                    sha_str = Color.wrap(Color.YELLOW, sha[:7] if sha else "unknown")
                    line = f"{prefix}{sha_str} {b}"
                    
                    if verbose > 1 and not is_remote:
                        remote = config.get(f"branch.{b}.remote")
                        merge = config.get(f"branch.{b}.merge")
                        if remote and merge:
                            line += f" [{Color.wrap(Color.BLUE, remote)}/{Color.wrap(Color.CYAN, merge.replace('refs/heads/', ''))}]"

                if b == current:
                    print(Color.wrap(Color.GREEN, line))
                else:
                    print(line)
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
