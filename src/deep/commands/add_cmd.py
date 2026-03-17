"""
deep.commands.add_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~
DeepGit ``add`` command implementation.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional, Tuple, List

from deep.core.ignore import IgnoreEngine
from deep.core.reconcile import sanitize_path
from deep.storage.index import add_multiple_to_index, remove_multiple_from_index
from deep.storage.objects import Blob, write_object
from deep.core.repository import DEEP_DIR, find_repo
from deep.utils.ux import ProgressBar


from concurrent.futures import ThreadPoolExecutor, as_completed

def _add_file_worker(repo_root: Path, dg_dir: Path, file_path: Path, previous_sha: Optional[str] = None, previous_size: Optional[int] = None, previous_mtime_ns: Optional[int] = None) -> tuple[str, Optional[str], int, int]:
    """Worker function to process a single file. (Must be top-level for pickling)"""
    from deep.storage.objects import Blob, write_object, write_delta_object, write_large_blob
    from deep.utils.ux import Color
    from deep.core.reconcile import sanitize_path
    
    rel_path = file_path.relative_to(repo_root).as_posix()
    rel_path, _ = sanitize_path(rel_path)
    
    # Fast Path: Check mtime and size before reading bytes
    stat = file_path.stat()
    if previous_sha is not None and previous_size == stat.st_size and previous_mtime_ns == stat.st_mtime_ns:
        # Heuristic says file hasn't changed
        return rel_path, None, stat.st_size, stat.st_mtime_ns

    if sha == previous_sha:
        # Content hasn't changed, just return the existing info with updated stat
        return rel_path, sha, stat.st_size, stat.st_mtime_ns

    # Content changed, write new object
    objects_dir = dg_dir / "objects"
    
    # Phase 2: Content Deduplication
    # If file is large (> 128KB), use chunking
    if stat.st_size > 128 * 1024:
        sha = write_large_blob(objects_dir, data)
    # Phase 1: Try Delta Compression if we have a previous SHA
    elif previous_sha:
        sha = write_delta_object(objects_dir, previous_sha, data)
    else:
        sha = write_object(objects_dir, Blob(data))
        
    return rel_path, sha, stat.st_size, stat.st_mtime_ns


def run(args) -> None:  # type: ignore[no-untyped_def]
    """Execute the ``add`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"DeepGit: error: {exc}", file=sys.stderr)
        sys.exit(1)

    dg_dir = repo_root / DEEP_DIR
    objects_dir = dg_dir / "objects"

    from deep.storage.index import read_index
    index = read_index(dg_dir)
    ignore_engine = IgnoreEngine(repo_root)
    
    files_to_add: list[Path] = []
    paths_to_remove: list[str] = []

    for file_path_str in args.files:
        path = Path(file_path_str).absolute()
        if not path.exists():
            # Handle staging of deletions
            try:
                rel_path = path.relative_to(repo_root).as_posix()
                rel_path, _ = sanitize_path(rel_path)
            except ValueError:
                # Path is outside repo
                print(f"DeepGit: error: {file_path_str} is outside repository", file=sys.stderr)
                sys.exit(1)
                
            if rel_path in index.entries:
                paths_to_remove.append(rel_path)
                continue
            else:
                print(f"DeepGit: error: {file_path_str} does not exist", file=sys.stderr)
                sys.exit(1)
            
        if path.is_file():
            files_to_add.append(path)
        elif path.is_dir():
            for dirpath, dirnames, filenames in os.walk(path):
                rel_dir = Path(dirpath).relative_to(repo_root).as_posix()
                
                valid_dirs = []
                for d in dirnames:
                    d_rel = f"{rel_dir}/{d}" if rel_dir != "." else d
                    if d == DEEP_DIR:
                        continue
                    if not ignore_engine.is_ignored(d_rel, is_dir=True):
                        valid_dirs.append(d)
                dirnames[:] = valid_dirs
                
                for f in filenames:
                    f_rel = f"{rel_dir}/{f}" if rel_dir != "." else f
                    if not ignore_engine.is_ignored(f_rel, is_dir=False):
                        files_to_add.append(Path(dirpath) / f)

    if paths_to_remove:
        remove_multiple_from_index(dg_dir, paths_to_remove)
        for p in paths_to_remove:
            print(f"DeepGit: staged deletion: {p}")

    if not files_to_add:
        return

    # Phase 1: Parallel Processing
    # No need to re-read index here
    
    index_updates = []
    
    # Phase 1: Parallel Processing
    # No need to re-read index here
    max_workers = min(os.cpu_count() or 4, len(files_to_add))
    
    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = []
        for file_path in files_to_add:
            rel_path = file_path.relative_to(repo_root).as_posix()
            
            p_sha = None
            p_size = None
            p_mtime = None
            
            if rel_path in index.entries:
                entry = index.entries[rel_path]
                p_sha = entry.content_hash
                p_size = entry.size
                p_mtime_ns = entry.mtime_ns
            
            futures.append(executor.submit(
                _add_file_worker, 
                repo_root, 
                dg_dir, 
                file_path, 
                p_sha,
                p_size,
                p_mtime_ns
            ))
            
        for future in as_completed(futures):
            results.append(future.result())
        
    if results:
        # Filter results to only those that actually changed (SHA is not None)
        # OR were previously staged but with different stats (SHA is not None)
        # We also need to keep track of files that returned SHA=None because they were skipped by heuristic
        # but those don't need update_multiple_index_entries.
        
        actual_results = [r for r in results if r[1] is not None]
        
        if actual_results:
            add_multiple_to_index(dg_dir, actual_results)
            print(f"DeepGit: added {len(actual_results)} files to the index.")
