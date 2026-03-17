"""
deep.commands.mv_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~
DeepGit ``mv <source> <destination>`` command implementation.

Moves or renames a file, directory, or symlink and updates the index.
"""

from __future__ import annotations

import os
import sys
import shutil
from pathlib import Path

from deep.storage.index import DeepIndex, DeepIndexEntry, read_index, write_index
from deep.storage.objects import Blob
from deep.core.repository import DEEP_DIR, find_repo


def run(args) -> None:  # type: ignore[no-untyped-def]
    """Execute the ``mv`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"DeepGit: error: {exc}", file=sys.stderr)
        sys.exit(1)

    dg_dir = repo_root / DEEP_DIR
    objects_dir = dg_dir / "objects"

    src_path_str = args.source
    dest_path_str = args.destination

    src_path = Path(src_path_str).resolve()
    dest_path = Path(dest_path_str).resolve()

    if not src_path.exists():
        print(f"DeepGit: error: bad source, source={src_path_str}, destination={dest_path_str}", file=sys.stderr)
        sys.exit(1)

    rel_src = src_path.relative_to(repo_root).as_posix()

    if dest_path.is_dir():
        dest_path = dest_path / src_path.name
        
    rel_dest = dest_path.relative_to(repo_root).as_posix()

    if dest_path.exists():
        print(f"DeepGit: error: destination exists, source={src_path_str}, destination={dest_path_str}", file=sys.stderr)
        sys.exit(1)

    # 1. Move file on disk
    shutil.move(str(src_path), str(dest_path))

    # 2. Update index
    from deep.storage.index import read_index_no_lock, write_index_no_lock
    from deep.core.locks import RepositoryLock
    
    repo_lock = RepositoryLock(dg_dir)
    with repo_lock:
        index = read_index_no_lock(dg_dir)
        to_remove = []
        to_update = {} # path -> entry
        
        if rel_src in index.entries:
            # Single file move
            entry = index.entries[rel_src]
            to_remove.append(rel_src)
            # Re-stat the moved file
            stat = dest_path.stat()
            import hashlib
            to_update[rel_dest] = DeepIndexEntry(
                content_hash=entry.content_hash, 
                size=stat.st_size, 
                mtime_ns=int(stat.st_mtime * 1e9),
                path_hash=hashlib.sha1(rel_dest.encode()).hexdigest()
            )
        else:
            # Directory move (look for prefix)
            prefix = rel_src + "/"
            for path, entry in index.entries.items():
                if path.startswith(prefix):
                    new_path = rel_dest + path[len(rel_src):]
                    to_remove.append(path)
                    try:
                        stat = (repo_root / new_path).stat()
                        import hashlib
                        to_update[new_path] = DeepIndexEntry(
                            content_hash=entry.content_hash, 
                            size=stat.st_size, 
                            mtime_ns=int(stat.st_mtime * 1e9),
                            path_hash=hashlib.sha1(new_path.encode()).hexdigest()
                        )
                    except FileNotFoundError:
                        pass

        for p in to_remove:
            if p in index.entries:
                del index.entries[p]
        for p, e in to_update.items():
            index.entries[p] = e
            
        write_index_no_lock(dg_dir, index)

    print(f"Renamed {rel_src} -> {rel_dest}")
