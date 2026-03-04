"""
deep_git.commands.branch_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep-git branch [name]`` command implementation.
"""

from __future__ import annotations

import sys
from pathlib import Path

from deep_git.core.refs import (
    get_current_branch,
    list_branches,
    resolve_head,
    update_branch,
)
from deep_git.core.repository import DEEP_GIT_DIR, find_repo
from deep_git.core.utils import Color


def run(args) -> None:  # type: ignore[no-untyped-def]
    """Execute the ``branch`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    dg_dir = repo_root / DEEP_GIT_DIR

    if args.name is None:
        # List branches.
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

    # Create a new branch.
    head_sha = resolve_head(dg_dir)
    if head_sha is None:
        print("Error: cannot create branch without any commits", file=sys.stderr)
        sys.exit(1)
    update_branch(dg_dir, args.name, head_sha)
    print(f"Created branch '{args.name}' at {head_sha[:7]}")
