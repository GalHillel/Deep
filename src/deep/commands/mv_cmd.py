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
from deep.storage.transaction import TransactionManager


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

    # Use absolute paths for physical disk operations
    src_abs = Path(src_path_str).absolute()
    dest_abs = Path(dest_path_str).absolute()

    if not src_abs.exists():
        print(f"Deep: error: bad source, source={src_path_str}", file=sys.stderr)
        raise DeepCLIException(1)

    try:
        rel_src = src_abs.relative_to(repo_root).as_posix()
    except ValueError:
        print(f"Deep: error: source '{src_path_str}' is outside the repository.", file=sys.stderr)
        raise DeepCLIException(1)

    # 1. Determine if moving into a folder
    if dest_abs.is_dir():
        dest_abs = dest_abs / src_abs.name
        
    try:
        rel_dest = dest_abs.relative_to(repo_root).as_posix()
    except ValueError:
        print(f"Deep: error: destination '{dest_path_str}' is outside the repository.", file=sys.stderr)
        raise DeepCLIException(1)

    if dest_abs.exists():
        print(f"Deep: error: destination exists, source={src_path_str}, destination={dest_path_str}", file=sys.stderr)
        raise DeepCLIException(1)

    # 2. Collect targeted tracked files
    from deep.storage.index import read_index_no_lock, write_index_no_lock
    index = read_index_no_lock(dg_dir)
    to_remove: list[str] = []
    to_update: dict[str, DeepIndexEntry] = {}
    
    import hashlib
    import struct

    if rel_src in index.entries:
        # Single file move
        entry = index.entries[rel_src]
        to_remove.append(rel_src)
        
        stat = src_abs.stat()
        path_hash_full = hashlib.sha256(rel_dest.encode()).digest()
        path_hash_int = struct.unpack(">Q", path_hash_full[:8])[0]
        to_update[rel_dest] = DeepIndexEntry(
            content_hash=entry.content_hash, 
            mtime_ns=stat.st_mtime_ns,
            size=stat.st_size, 
            path_hash=path_hash_int
        )
    else:
        # Directory or untracked file check
        prefix = f"{rel_src}/" if rel_src != "." else ""
        for path, entry in index.entries.items():
            if path == rel_src or path.startswith(prefix):
                # Calculate new relative path
                suffix = path[len(rel_src):].lstrip("/")
                new_rel = f"{rel_dest}/{suffix}" if suffix else rel_dest
                
                to_remove.append(path)
                
                # We'll re-stat the actual disk file for metadata accuracy
                try:
                    stat = (repo_root / path).stat()
                    path_hash_full = hashlib.sha256(new_rel.encode()).digest()
                    path_hash_int = struct.unpack(">Q", path_hash_full[:8])[0]
                    to_update[new_rel] = DeepIndexEntry(
                        content_hash=entry.content_hash, 
                        mtime_ns=stat.st_mtime_ns,
                        size=stat.st_size, 
                        path_hash=path_hash_int
                    )
                except FileNotFoundError:
                    # File was deleted from disk but is in index (should still be "moved" in index)
                    path_hash_full = hashlib.sha256(new_rel.encode()).digest()
                    path_hash_int = struct.unpack(">Q", path_hash_full[:8])[0]
                    to_update[new_rel] = entry._replace(path_hash=path_hash_int)

    if not to_remove:
        print(f"Deep: error: source '{src_path_str}' is not tracked.", file=sys.stderr)
        raise DeepCLIException(1)

    # 3. Perform move and update index in a transaction
    with TransactionManager(dg_dir) as tm:
        tm.begin("mv", details=f"{rel_src} -> {rel_dest}")
        
        # Ensure destination directory exists
        dest_abs.parent.mkdir(parents=True, exist_ok=True)
        
        # Physical move
        shutil.move(str(src_abs), str(dest_abs))
        
        # Index update
        for p in to_remove:
            if p in index.entries:
                del index.entries[p]
        for p, e in to_update.items():
            index.entries[p] = e
            
        write_index_no_lock(dg_dir, index)
        tm.commit()

    print(f"Renamed {rel_src} -> {rel_dest}")
