"""
deep.commands.mv_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep mv <source> <destination>`` command implementation.

Moves or renames a file, directory, or symlink and updates the index.
"""

from __future__ import annotations

import os
import sys
import shutil
from pathlib import Path

from deep.storage.index import remove_index_entry, update_index_entry
from deep.storage.objects import Blob
from deep.core.repository import DEEP_GIT_DIR, find_repo


def run(args) -> None:  # type: ignore[no-untyped-def]
    """Execute the ``mv`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    dg_dir = repo_root / DEEP_GIT_DIR
    objects_dir = dg_dir / "objects"

    src_path_str = args.source
    dest_path_str = args.destination

    src_path = Path(src_path_str).resolve()
    dest_path = Path(dest_path_str).resolve()

    if not src_path.exists():
        print(f"fatal: bad source, source={src_path_str}, destination={dest_path_str}", file=sys.stderr)
        sys.exit(1)

    rel_src = src_path.relative_to(repo_root).as_posix()

    if dest_path.is_dir():
        dest_path = dest_path / src_path.name
        
    rel_dest = dest_path.relative_to(repo_root).as_posix()

    if dest_path.exists():
        print(f"fatal: destination exists, source={src_path_str}, destination={dest_path_str}", file=sys.stderr)
        sys.exit(1)

    # 1. Move file on disk
    shutil.move(str(src_path), str(dest_path))

    # 2. Update index
    if src_path.is_file() or dest_path.is_file():
        # Remove old entry if tracked
        try:
            remove_index_entry(dg_dir, rel_src)
        except KeyError:
            pass # Source was not tracked

        # Add new entry
        data = dest_path.read_bytes()
        blob = Blob(data=data)
        sha = blob.write(objects_dir)

        stat = dest_path.stat()
        update_index_entry(
            dg_dir,
            rel_path=rel_dest,
            sha=sha,
            size=stat.st_size,
            mtime=stat.st_mtime,
        )
    elif dest_path.is_dir():
        # Move directory recursively
        # Since we just moved the dir, we need to iterate over the new directory
        for dirpath, dirnames, filenames in os.walk(dest_path):
            rel_dir = Path(dirpath).relative_to(repo_root).as_posix()
            old_rel_dir = rel_src + rel_dir[len(rel_dest):]
            
            for f in filenames:
                f_new = f"{rel_dir}/{f}" if rel_dir != "." else f
                f_old = f"{old_rel_dir}/{f}" if old_rel_dir != "." else f
                
                # Remove old entry
                try:
                    remove_index_entry(dg_dir, f_old)
                except KeyError:
                    pass
                
                # Add new entry
                child_dest = Path(dirpath) / f
                data = child_dest.read_bytes()
                blob = Blob(data=data)
                sha = blob.write(objects_dir)

                stat = child_dest.stat()
                update_index_entry(
                    dg_dir,
                    rel_path=f_new,
                    sha=sha,
                    size=stat.st_size,
                    mtime=stat.st_mtime,
                )

    print(f"Renamed {rel_src} -> {rel_dest}")
