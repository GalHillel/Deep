"""
deep_git.commands.log_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep-git log`` command implementation.
"""

from __future__ import annotations

import sys
from pathlib import Path

from deep_git.core.objects import Commit, read_object
from deep_git.core.refs import log_history, resolve_head
from deep_git.core.repository import DEEP_GIT_DIR, find_repo


def run(args) -> None:  # type: ignore[no-untyped-def]
    """Execute the ``log`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    dg_dir = repo_root / DEEP_GIT_DIR
    objects_dir = dg_dir / "objects"

    shas = log_history(dg_dir)
    if not shas:
        print("No commits yet.")
        return

    for sha in shas:
        obj = read_object(objects_dir, sha)
        if not isinstance(obj, Commit):
            continue
        print(f"commit {sha}")
        print(f"Author: {obj.author}")
        print(f"Date:   {obj.timestamp} {obj.timezone}")
        print()
        for line in obj.message.splitlines():
            print(f"    {line}")
        print()
