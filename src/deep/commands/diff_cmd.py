"""
deep.commands.diff_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep diff`` command implementation.
"""

from __future__ import annotations
from deep.core.errors import DeepCLIException

import sys
from pathlib import Path

from deep.core.diff import diff_working_tree
from deep.core.repository import find_repo, DEEP_DIR


def run(args) -> None:  # type: ignore[no-untyped_def]
    """Execute the ``diff`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Deep: error: {exc}", file=sys.stderr)
        raise DeepCLIException(1)

    dg_dir = repo_root / DEEP_DIR
    from deep.core.refs import resolve_revision
    from deep.core.diff import diff_trees, diff_working_tree
    
    # Handle revisions from args
    revisions = getattr(args, "revisions", [])
    cached = getattr(args, "cached", False)
    
    if len(revisions) >= 2:
        rev1 = resolve_revision(dg_dir, revisions[0])
        rev2 = resolve_revision(dg_dir, revisions[1])
        if not rev1 or not rev2:
            print(f"Deep: error: Invalid revisions {revisions}", file=sys.stderr)
            raise DeepCLIException(1)
        diffs = diff_trees(dg_dir, rev1, rev2)
    elif len(revisions) == 1:
        rev1 = resolve_revision(dg_dir, revisions[0])
        if not rev1:
            print(f"Deep: error: Invalid revision {revisions[0]}", file=sys.stderr)
            raise DeepCLIException(1)
        # diff <rev> is rev vs working tree (via index)
        diffs = diff_trees(dg_dir, rev1, "HEAD")
    elif cached:
        from deep.core.diff import diff_index_vs_head
        diffs = diff_index_vs_head(repo_root)
    else:
        diffs = diff_working_tree(repo_root)

    if not diffs:
        return  # no output = no differences

    for rel_path, diff_text in diffs:
        print(f"\033[1;36mdiff --deep a/{rel_path} b/{rel_path}\033[0m")
        # Coloured output for diff lines.
        for line in diff_text.splitlines():
            if line.startswith("+++") or line.startswith("---"):
                print(f"\033[1;36m{line}\033[0m") # cyan bold
            elif line.startswith("+"):
                print(f"\033[32m{line}\033[0m") # green
            elif line.startswith("-"):
                print(f"\033[31m{line}\033[0m") # red
            elif line.startswith("@@"):
                print(f"\033[33m{line}\033[0m") # yellow
            else:
                print(line)
