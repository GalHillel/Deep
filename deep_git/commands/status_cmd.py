"""
deep_git.commands.status_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deepgit status`` command implementation.
"""

from __future__ import annotations

import sys
from pathlib import Path

from deep_git.core.refs import get_current_branch, resolve_head
from deep_git.core.repository import DEEP_GIT_DIR, find_repo
from deep_git.core.status import compute_status
from deep_git.core.utils import Color


def run(args) -> None:  # type: ignore[no-untyped-def]
    """Execute the ``status`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    dg_dir = repo_root / DEEP_GIT_DIR
    branch = get_current_branch(dg_dir)
    if branch:
        print(f"On branch {branch}")
    else:
        head_sha = resolve_head(dg_dir)
        print(f"HEAD detached at {head_sha[:7]}" if head_sha else "HEAD detached")
    print()

    status = compute_status(repo_root)

    has_staged = status.staged_new or status.staged_modified or status.staged_deleted
    has_unstaged = status.modified or status.deleted

    if has_staged:
        print("Changes to be committed:")
        for f in status.staged_new:
            print(f"  {Color.wrap(Color.GREEN, 'new file:   ' + f)}")
        for f in status.staged_modified:
            print(f"  {Color.wrap(Color.GREEN, 'modified:   ' + f)}")
        for f in status.staged_deleted:
            print(f"  {Color.wrap(Color.GREEN, 'deleted:    ' + f)}")
        print()

    if has_unstaged:
        print("Changes not staged for commit:")
        for f in status.modified:
            print(f"  {Color.wrap(Color.RED, 'modified:   ' + f)}")
        for f in status.deleted:
            print(f"  {Color.wrap(Color.RED, 'deleted:    ' + f)}")
        print()

    if status.untracked:
        print("Untracked files:")
        for f in status.untracked:
            print(f"  {Color.wrap(Color.RED, f)}")
        print()

    if not has_staged and not has_unstaged and not status.untracked:
        print("nothing to commit, working tree clean")
