"""
deep_git.commands.add_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep-git add <file>`` command implementation.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from deep_git.core.index import update_index_entry
from deep_git.core.objects import Blob
from deep_git.core.repository import DEEP_GIT_DIR, find_repo


def run(args) -> None:  # type: ignore[no-untyped-def]
    """Execute the ``add`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    dg_dir = repo_root / DEEP_GIT_DIR
    objects_dir = dg_dir / "objects"

    for file_path_str in args.files:
        file_path = Path(file_path_str).resolve()
        if not file_path.is_file():
            print(f"Error: {file_path_str} is not a file", file=sys.stderr)
            sys.exit(1)

        data = file_path.read_bytes()
        blob = Blob(data=data)
        sha = blob.write(objects_dir)

        # Relative path using forward slashes for portability.
        rel_path = file_path.relative_to(repo_root).as_posix()
        stat = file_path.stat()

        update_index_entry(
            dg_dir,
            rel_path=rel_path,
            sha=sha,
            size=stat.st_size,
            mtime=stat.st_mtime,
        )
        print(f"add '{rel_path}'")
