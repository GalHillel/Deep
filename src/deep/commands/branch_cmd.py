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
        # 1. Handle Deletion
        if getattr(args, "delete", False):
            if not args.name:
                print("Deep: error: branch name required for deletion", file=sys.stderr)
                raise DeepCLIException(1)
            
            tm.begin("branch_delete")
            from deep.core.refs import delete_branch
            try:
                delete_branch(dg_dir, args.name)
                print(f"Deleted branch '{args.name}'.")
                tm.commit()
            except Exception as e:
                print(f"Deep: error: {e}", file=sys.stderr)
                # Cleanup transaction if failed? TransactionManager handle it usually
                raise DeepCLIException(1)
            return

        # 2. Handle Listing (Default if no name provided)
        if args.name is None:
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

            verboseTotal = getattr(args, "verbose", 0)
            if getattr(args, "vv", False):
                verboseTotal = 2
            
            for b in branches:
                is_remote = b.startswith("remotes/")
                current_sha = None
                
                prefix = "* " if b == current else "  "
                
                if verboseTotal > 0:
                    from deep.core.refs import get_branch, get_remote_ref
                    if is_remote:
                        # Format: remotes/<remote>/<branch>
                        parts = b.split("/", 2)
                        if len(parts) >= 3:
                            current_sha = get_remote_ref(dg_dir, parts[1], parts[2])
                    else:
                        current_sha = get_branch(dg_dir, b)
                    
                    sha_display = Color.wrap(Color.YELLOW, current_sha[:7] if current_sha else "unknown")
                    line = f"{prefix}{sha_display} {b}"
                else:
                    line = f"{prefix}{b}"
                
                if verboseTotal > 1 and not is_remote:
                    # Show tracking info
                    remote_tracking = config.get(f"branch.{b}.remote")
                    merge_tracking = config.get(f"branch.{b}.merge")
                    if remote_tracking and merge_tracking:
                        short_merge = merge_tracking.replace("refs/heads/", "")
                        line += f" [{Color.wrap(Color.BLUE, remote_tracking)}/{Color.wrap(Color.CYAN, short_merge)}]"

                if b == current:
                    print(Color.wrap(Color.GREEN, line))
                else:
                    color_line = Color.wrap(Color.RED, line) if is_remote else line
                    print(color_line)
            return

        # 3. Handle Creation
        if not args.name:
            # Should be handled by argparse or listing logic above, but safety check
            raise DeepCLIException(1)
            
        tm.begin("branch_create")
        from deep.core.refs import resolve_revision
        start_point = getattr(args, "start_point", "HEAD")
        target_sha = resolve_revision(dg_dir, start_point)
        
        if target_sha is None:
            print(f"Deep: error: Not a valid object name: '{start_point}'", file=sys.stderr)
            raise DeepCLIException(1)
            
        from deep.core.refs import update_branch
        update_branch(dg_dir, args.name, target_sha)
        print(f"Created branch '{args.name}' at {target_sha[:7]}")
        tm.commit()
