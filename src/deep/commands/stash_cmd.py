"""
deep.commands.stash_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep stash [save|pop|list]`` command implementation.
"""

from __future__ import annotations

import sys
from pathlib import Path

from deep.core.repository import DEEP_GIT_DIR, find_repo
from deep.core.stash import get_stash_list, pop_stash, save_stash


def run(args) -> None:  # type: ignore[no-untyped-def]
    """Execute the ``stash`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    action = getattr(args, "action", "save") or "save"

    dg_dir = repo_root / DEEP_GIT_DIR

    if action in ("save", "push"):
        sha = save_stash(repo_root)
        if sha:
            print(f"Saved working directory and index state WIP: {sha[:7]}")
        else:
            print("No local changes to save")
    elif action == "list":
        stashes = get_stash_list(dg_dir)
        if not stashes:
            print("No stash entries found.")
            return
        
        # Invert to show newest stash (stack top) first
        stashes.reverse()
        from deep.storage.objects import Commit, read_object
        objects_dir = dg_dir / "objects"
        for i, sha in enumerate(stashes):
            commit = read_object(objects_dir, sha)
            assert isinstance(commit, Commit)
            print(f"stash@{{{i}}}: {commit.message}")
    elif action == "pop":
        success = pop_stash(repo_root)
        if not success:
            sys.exit(1)
    else:
        print(f"Unknown stash action: {action}", file=sys.stderr)
        sys.exit(1)
