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
from deep.core.stash import apply_stash, clear_stash, drop_stash, get_stash_list, pop_stash, save_stash


def run(args) -> None:  # type: ignore[no-untyped-def]
    """Execute the ``stash`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Deep: error: {exc}", file=sys.stderr)
        raise DeepCLIException(1)

    action = getattr(args, "action", "save") or "save"
    message = getattr(args, "message", None)

    dg_dir = repo_root / DEEP_DIR

    if action in ("save", "push"):
        sha = save_stash(repo_root, message=message)
        if sha:
            print(f"Saved working directory and index state WIP: {sha[:7]}")
        else:
            print("No local changes to save")
    elif action == "list":
        stashes = get_stash_list(dg_dir)
        if not stashes:
            # Match git output: nothing to show
            return
        
        # Invert to show newest stash (stack top) first
        stashes_reversed = list(reversed(stashes))
        from deep.storage.objects import Commit, read_object
        objects_dir = dg_dir / "objects"
        for i, sha in enumerate(stashes_reversed):
            try:
                commit = read_object(objects_dir, sha)
                if isinstance(commit, Commit):
                    print(f"stash@{{{i}}}: {commit.message}")
            except (FileNotFoundError, ValueError):
                print(f"stash@{{{i}}}: [broken object {sha[:7]}]")
    elif action == "pop":
        try:
            success = pop_stash(repo_root)
            if not success:
                raise DeepCLIException(1)
        except RuntimeError as e:
            print(f"Deep: error: {e}", file=sys.stderr)
            raise DeepCLIException(1)
    elif action == "apply":
        # Check if message contains an index like "0" or "stash@{0}"
        index = 0
        if message:
            import re
            m = re.search(r"(\d+)", message)
            if m:
                index = int(m.group(1))
        try:
            success = apply_stash(repo_root, index=index)
            if not success:
                raise DeepCLIException(1)
        except RuntimeError as e:
            print(f"Deep: error: {e}", file=sys.stderr)
            raise DeepCLIException(1)
    elif action == "drop":
        index = 0
        if message:
            import re
            m = re.search(r"(\d+)", message)
            if m:
                index = int(m.group(1))
        try:
            drop_stash(repo_root, index=index)
        except RuntimeError as e:
            print(f"Deep: error: {e}", file=sys.stderr)
            raise DeepCLIException(1)
    elif action == "clear":
        clear_stash(repo_root)
    else:
        print(f"Unknown stash action: {action}", file=sys.stderr)
        raise DeepCLIException(1)
