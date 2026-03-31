"""
deep.commands.stash_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep stash [save|pop|list]`` command implementation.
"""

from __future__ import annotations
from deep.core.errors import DeepCLIException

import sys
from pathlib import Path

from deep.core.constants import DEEP_DIR
from deep.core.repository import find_repo

import argparse
from typing import Any

def setup_parser(subparsers: Any) -> None:
    """Set up the 'stash' command parser."""
    p_stash = subparsers.add_parser(
        "stash",
        help="Stash temporary changes",
        description="""Save your local modifications to a temporary stack and reset the working directory to match the HEAD commit.

This allows you to quickly switch contexts without committing unfinished work.""",
        epilog="""

\033[1mEXAMPLES:\033[0m
  \033[1;34m⚓️ deep stash\033[0m
     Save current changes to a new stash entry
  \033[1;34m⚓️ deep stash list\033[0m
     View all current stashed changes
  \033[1;34m⚓️ deep stash pop\033[0m
     Apply the most recent stash and remove it from the stack
  \033[1;34m⚓️ deep stash apply\033[0m
     Apply the most recent stash but keep it in the stack
  \033[1;34m⚓️ deep stash drop\033[0m
     Discard the most recent stash entry
""",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    p_stash.add_argument("action", choices=["push", "save", "pop", "list", "drop", "clear", "apply"], nargs="?", default="save", help="The stash operation to perform (default: save)")
from deep.core.stash import get_stash_list, pop_stash, save_stash

def run(args) -> None:  # type: ignore[no-untyped-def]
    """Execute the ``stash`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Deep: error: {exc}", file=sys.stderr)
        raise DeepCLIException(1)

    action = getattr(args, "action", "save") or "save"

    dg_dir = repo_root / DEEP_DIR

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
            raise DeepCLIException(1)
    else:
        print(f"Unknown stash action: {action}", file=sys.stderr)
        raise DeepCLIException(1)
