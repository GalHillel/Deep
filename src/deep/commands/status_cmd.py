"""
deep.commands.status_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep status`` command implementation.
"""

from __future__ import annotations
from deep.core.errors import DeepCLIException

import sys
from pathlib import Path

from deep.core.refs import get_current_branch, resolve_head
from deep.core.constants import DEEP_DIR
from deep.core.repository import find_repo
from deep.core.status import compute_status
from deep.utils.ux import Color


def run(args) -> None:  # type: ignore[no-untyped-def]
    """Execute the ``status`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Deep: error: {exc}", file=sys.stderr)
        raise DeepCLIException(1)

    dg_dir = repo_root / DEEP_DIR
    branch = get_current_branch(dg_dir)
    if branch:
        print(f"On branch {Color.wrap(Color.CYAN, branch)}")
    else:
        head_sha = resolve_head(dg_dir)
        detached_msg = f"HEAD detached at {head_sha[:7]}" if head_sha else "HEAD detached"
        print(Color.wrap(Color.YELLOW, detached_msg))
    print()

    status = compute_status(repo_root)

    if getattr(args, "porcelain", False):
        # Porcelain format: <status_code> <path>
        for f in status.staged_new: print(f"A  {f}")
        for f in status.staged_modified: print(f"M  {f}")
        for f in status.staged_deleted: print(f"D  {f}")
        for f in status.modified: print(f" M {f}")
        for f in status.deleted: print(f" D {f}")
        for f in status.untracked: print(f"?? {f}")
        return

    # Tracking info
    if status.remote:
        if status.ahead_count > 0 and status.behind_count > 0:
            print(f"Your branch and '{status.remote}/{status.remote_branch}' have diverged,")
            print(f"and have {status.ahead_count} and {status.behind_count} different commits each, respectively.")
        elif status.ahead_count > 0:
            print(f"Your branch is ahead of '{status.remote}/{status.remote_branch}' by {status.ahead_count} commits.")
        elif status.behind_count > 0:
            print(f"Your branch is behind '{status.remote}/{status.remote_branch}' by {status.behind_count} commits.")
        else:
            print(f"Your branch is up to date with '{status.remote}/{status.remote_branch}'.")
        print()

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
        print(Color.wrap(Color.GREEN, "nothing to commit, working tree clean"))
