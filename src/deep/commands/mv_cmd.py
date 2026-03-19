"""
deep.commands.mv_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~
Deep ``mv <source> <destination>`` command implementation.

Moves or renames a file, directory, or symlink and updates the index.
"""

from __future__ import annotations
from deep.core.errors import DeepCLIException

import os
import sys
import shutil
import hashlib
import struct
from pathlib import Path

from deep.storage.index import DeepIndex, DeepIndexEntry, read_index, write_index
from deep.storage.objects import Blob
from deep.core.constants import DEEP_DIR
from deep.core.repository import find_repo


def run(args) -> None:  # type: ignore[no-untyped-def]
    """Execute the ``mv`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Deep: error: {exc}", file=sys.stderr)
        raise DeepCLIException(1)

    dg_dir = repo_root / DEEP_DIR
    objects_dir = dg_dir / "objects"

    src_path_str = args.source
    dest_path_str = args.destination

    src_path = Path(src_path_str).resolve()
    dest_path = Path(dest_path_str).resolve()

    if not src_path.exists():
        print(f"Deep: error: bad source, source={src_path_str}, destination={dest_path_str}", file=sys.stderr)
        raise DeepCLIException(1)

    rel_src = src_path.relative_to(repo_root).as_posix()

    if dest_path.is_dir():
        dest_path = dest_path / src_path.name
        
    rel_dest = dest_path.relative_to(repo_root).as_posix()

    if dest_path.exists():
        print(f"Deep: error: destination exists, source={src_path_str}, destination={dest_path_str}", file=sys.stderr)
        raise DeepCLIException(1)

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
            path_hash_full = hashlib.sha256(rel_dest.encode()).digest()
            path_hash_int = struct.unpack(">Q", path_hash_full[:8])[0]
            to_update[rel_dest] = DeepIndexEntry(
                content_hash=entry.content_hash, 
                mtime_ns=int(stat.st_mtime * 1e9),
                size=stat.st_size, 
                path_hash=path_hash_int
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
                        path_hash_full = hashlib.sha256(new_path.encode()).digest()
                        path_hash_int = struct.unpack(">Q", path_hash_full[:8])[0]
                        to_update[new_path] = DeepIndexEntry(
                            content_hash=entry.content_hash, 
                            mtime_ns=int(stat.st_mtime * 1e9),
                            size=stat.st_size, 
                            path_hash=path_hash_int
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
