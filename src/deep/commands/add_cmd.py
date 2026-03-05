"""
deep.commands.add_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep-git add <file>`` command implementation.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from deep.core.ignore import IgnoreEngine
from deep.storage.index import update_multiple_index_entries
from deep.storage.objects import Blob, write_object
from deep.core.repository import DEEP_GIT_DIR, find_repo
from deep.utils.ux import ProgressBar


from concurrent.futures import ThreadPoolExecutor, as_completed

def _add_file_worker(repo_root: Path, dg_dir: Path, file_path: Path, previous_sha: Optional[str] = None) -> tuple[str, str, int, float]:
    """Worker function to process a single file. (Must be top-level for pickling)"""
    from deep.storage.objects import Blob, write_object, write_delta_object, write_large_blob
    
    rel_path = file_path.relative_to(repo_root).as_posix()
    data = file_path.read_bytes()
    stat = file_path.stat()
    
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
        
    return rel_path, sha, stat.st_size, stat.st_mtime


def run(args) -> None:  # type: ignore[no-untyped_def]
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
            files_to_add.append(path)
        elif path.is_dir():
            for dirpath, dirnames, filenames in os.walk(path):
                rel_dir = Path(dirpath).relative_to(repo_root).as_posix()
                
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

    if not files_to_add:
        return

    # Phase 1: Parallel Processing
    from deep.storage.index import read_index
    index = read_index(dg_dir)
    
    index_updates = []
    
    # We'll use more workers for large sets
    max_workers = min(os.cpu_count() or 4, len(files_to_add))
    
    print(f"Staging {len(files_to_add)} files using {max_workers} cores...")
    
    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = []
        for file_path in files_to_add:
            rel_path = file_path.relative_to(repo_root).as_posix()
            previous_sha = index.entries.get(rel_path).sha if rel_path in index.entries else None
            
            futures.append(executor.submit(
                _add_file_worker, 
                repo_root, 
                dg_dir, 
                file_path, 
                previous_sha
            ))
            
        from deep.utils.ux import ProgressBar
        with ProgressBar(total=len(futures), prefix="Staging") as pb:
            for i, future in enumerate(as_completed(futures)):
                results.append(future.result())
                pb.update(i + 1)
        
    if results:
        update_multiple_index_entries(dg_dir, results)
        print(f"Added {len(results)} files.")
