"""
deep_git.commands.diff_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deepgit diff`` command implementation.
"""

from __future__ import annotations

import sys
from pathlib import Path

from deep_git.core.diff import diff_working_tree
from deep_git.core.repository import find_repo


def run(args) -> None:  # type: ignore[no-untyped-def]
    """Execute the ``diff`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    diffs = diff_working_tree(repo_root)
    if not diffs:
        return  # no output = no differences

    for rel_path, diff_text in diffs:
        # Coloured output for diff lines.
        for line in diff_text.splitlines():
            if line.startswith("+++") or line.startswith("---"):
                print(f"\033[1m{line}\033[0m")
            elif line.startswith("+"):
                print(f"\033[32m{line}\033[0m")
            elif line.startswith("-"):
                print(f"\033[31m{line}\033[0m")
            elif line.startswith("@@"):
                print(f"\033[36m{line}\033[0m")
            else:
                print(line)
