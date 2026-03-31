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
from deep.utils.ux import DeepHelpFormatter, format_example
import argparse
from typing import Any


from deep.utils.ux import (
    DeepHelpFormatter, format_header, format_example, format_description
)
import argparse
from typing import Any


def setup_parser(subparsers: Any) -> None:
    """Set up the 'diff' command parser."""
    p_diff = subparsers.add_parser(
        "diff",
        help="Show changes between commits or worktree",
        description="""Show changes between the working tree and the index, or between two arbitrary commit objects.

Highly useful for reviewing modifications before staging or committing.""",
        epilog="""

\033[1mEXAMPLES:\033[0m
  \033[1;34m⚓️ deep diff\033[0m
     Compare worktree with the staging index
  \033[1;34m⚓️ deep diff HEAD\033[0m
     Compare worktree with the latest commit
  \033[1;34m⚓️ deep diff --cached\033[0m
     Show changes currently in the staging area
  \033[1;34m⚓️ deep diff main dev\033[0m
     Compare 'main' and 'dev' branches
  \033[1;34m⚓️ deep diff --stat\033[0m
     Show a summary of changes instead of full diff
""",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    p_diff.add_argument("--cached", "--staged", action="store_true", help="Show changes currently in the staging area")
    p_diff.add_argument("--stat", action="store_true", help="Show a summary of changes (insertions/deletions) instead of the full diff")
    p_diff.add_argument("revisions", nargs="*", help="Commit identifiers to compare (e.g., commit1 commit2, or just commit1)")


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

    stat = getattr(args, "stat", False)
    if stat:
        _print_diff_stat(diffs)
        return

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


def _print_diff_stat(diffs: list[tuple[str, str]]) -> None:
    """Print a summary of changes per file and a total summary."""
    total_files = len(diffs)
    total_ins = 0
    total_del = 0
    
    for rel_path, diff_text in diffs:
        ins = 0
        dele = 0
        for line in diff_text.splitlines():
            if line.startswith("+") and not line.startswith("+++"):
                ins += 1
            elif line.startswith("-") and not line.startswith("---"):
                dele += 1
        
        total_ins += ins
        total_del += dele
        
        # Simple bar representation
        combined = ins + dele
        if combined > 0:
            plus = "+" * ins
            minus = "-" * dele
            print(f" {rel_path:<40} | {combined:>3} {plus}{minus}")
        else:
            print(f" {rel_path:<40} |   0")

    files_label = "file changed" if total_files == 1 else "files changed"
    ins_label = "insertion(+)" if total_ins == 1 else "insertions(+)"
    del_label = "deletion(-)" if total_del == 1 else "deletions(-)"
    
    print(f"\n {total_files} {files_label}, {total_ins} {ins_label}, {total_del} {del_label}")
