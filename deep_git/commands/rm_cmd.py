"""
deep_git.commands.rm_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~
``deepgit rm <file>`` command implementation.

Removes a file from both the working directory and the index.
"""

from __future__ import annotations

import sys
from pathlib import Path

from deep_git.core.index import remove_index_entry
from deep_git.core.repository import DEEP_GIT_DIR, find_repo


def run(args) -> None:  # type: ignore[no-untyped-def]
    """Execute the ``rm`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    dg_dir = repo_root / DEEP_GIT_DIR

    for file_path_str in args.files:
        file_path = Path(file_path_str).resolve()
        rel_path = file_path.relative_to(repo_root).as_posix()

        # Remove from index.
        try:
            remove_index_entry(dg_dir, rel_path)
        except KeyError:
            print(f"Error: '{rel_path}' is not tracked.", file=sys.stderr)
            sys.exit(1)

        # Remove from working directory.
        if file_path.exists():
            file_path.unlink()

        print(f"rm '{rel_path}'")
