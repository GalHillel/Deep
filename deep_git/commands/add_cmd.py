"""
deep_git.commands.add_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep-git add <file>`` command implementation.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from deep_git.core.ignore import IgnoreEngine
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

    ignore_engine = IgnoreEngine(repo_root)
    files_to_add: list[Path] = []

    for file_path_str in args.files:
        path = Path(file_path_str).resolve()
        if not path.exists():
            print(f"Error: {file_path_str} does not exist", file=sys.stderr)
            sys.exit(1)
            
        if path.is_file():
            # Explicitly added files are always added, even if ignored.
            files_to_add.append(path)
        elif path.is_dir():
            # Recursively find files, respecting ignore rules.
            for dirpath, dirnames, filenames in os.walk(path):
                # Filter out ignored directories
                rel_dir = Path(dirpath).relative_to(repo_root).as_posix()
                
                # We need to filter dirnames in-place to prevent walking into them
                valid_dirs = []
                for d in dirnames:
                    d_rel = f"{rel_dir}/{d}" if rel_dir != "." else d
                    if d == DEEP_GIT_DIR:
                        continue
                    if not ignore_engine.is_ignored(d_rel, is_dir=True):
                        valid_dirs.append(d)
                dirnames[:] = valid_dirs
                
                for f in filenames:
                    f_rel = f"{rel_dir}/{f}" if rel_dir != "." else f
                    if not ignore_engine.is_ignored(f_rel, is_dir=False):
                        files_to_add.append(Path(dirpath) / f)

    for file_path in files_to_add:
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
