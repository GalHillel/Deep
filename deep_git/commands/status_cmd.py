"""
deep_git.commands.status_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deepgit status`` command implementation.
"""

from __future__ import annotations

import sys
from pathlib import Path

from deep_git.core.refs import get_current_branch
from deep_git.core.repository import DEEP_GIT_DIR, find_repo
from deep_git.core.status import compute_status


def run(args) -> None:  # type: ignore[no-untyped-def]
    """Execute the ``status`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    dg_dir = repo_root / DEEP_GIT_DIR
    branch = get_current_branch(dg_dir)
    print(f"On branch {branch or '(detached HEAD)'}")
    print()

    status = compute_status(repo_root)

    has_staged = status.staged_new or status.staged_modified or status.staged_deleted
    has_unstaged = status.modified or status.deleted

    if has_staged:
        print("Changes to be committed:")
        for f in status.staged_new:
            print(f"  \033[32mnew file:   {f}\033[0m")
        for f in status.staged_modified:
            print(f"  \033[32mmodified:   {f}\033[0m")
        for f in status.staged_deleted:
            print(f"  \033[32mdeleted:    {f}\033[0m")
        print()

    if has_unstaged:
        print("Changes not staged for commit:")
        for f in status.modified:
            print(f"  \033[31mmodified:   {f}\033[0m")
        for f in status.deleted:
            print(f"  \033[31mdeleted:    {f}\033[0m")
        print()

    if status.untracked:
        print("Untracked files:")
        for f in status.untracked:
            print(f"  \033[31m{f}\033[0m")
        print()

    if not has_staged and not has_unstaged and not status.untracked:
        print("nothing to commit, working tree clean")
