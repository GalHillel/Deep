"""
deep.commands.add_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~
Deep ``add`` command implementation.
"""

from __future__ import annotations
from deep.core.errors import DeepCLIException

import os
import sys
import hashlib
from pathlib import Path
from typing import Optional, Tuple, List

from deep.core.ignore import IgnoreEngine
from deep.core.reconcile import sanitize_path
from deep.storage.index import add_multiple_to_index, remove_multiple_from_index
from deep.storage.objects import Blob, write_object
from deep.core.constants import DEEP_DIR
from deep.core.repository import find_repo
from deep.utils.ux import ProgressBar


def get_description() -> str:
    return "Add file contents to the staging area (index) to be included in the next commit.\n\nThis prepares changes for recording."

def get_epilog() -> str:
    return """\033[1mEXAMPLES:\033[0m

  \033[1;34m⚓️ deep add file.txt\033[0m
     Add a specific file to the index.

  \033[1;34m⚓️ deep add .\033[0m
     Add all changed and new files in the current directory.

  \033[1;34m⚓️ deep add src/*.py\033[0m
     Add specific files using glob patterns.

  \033[1;34m⚓️ deep add -u\033[0m
     Add only updated files (not new ones).
"""

def setup_parser(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    p = subparsers.add_parser(
        "add",
        help="Add file contents to the staging index",
        description=get_description(),
        epilog=get_epilog(),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    p.add_argument("files", nargs="+", help="One or more files or directory paths to stage for commit")
    return p


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

    # Read and hash content
    data = file_path.read_bytes()
    sha = Blob(data=data).sha
    
    if sha == previous_sha:
        # Content hasn't changed, just return the existing info with updated stat
        return rel_path, sha, stat.st_size, stat.st_mtime_ns

    # Content changed, write new object
    objects_dir = dg_dir / "objects"
    
    # Phase 2: Content Deduplication
    # If file is large (> 128KB), use chunking
    if stat.st_size > 128 * 1024:
        from deep.storage.objects import write_large_blob
        sha = write_large_blob(objects_dir, data)
    # Phase 1: Try Delta Compression if we have a previous SHA
    elif previous_sha:
        from deep.storage.objects import write_delta_object
        sha = write_delta_object(objects_dir, previous_sha, data)
    else:
        from deep.storage.objects import write_object, Blob
        sha = write_object(objects_dir, Blob(data))
        
    return rel_path, sha, stat.st_size, stat.st_mtime_ns


def run(args) -> None:
    """Execute the ``add`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Deep: error: {exc}", file=sys.stderr)
        raise DeepCLIException(1)

    dg_dir = repo_root / DEEP_DIR
    objects_dir = dg_dir / "objects"

    from deep.storage.transaction import TransactionManager
    from deep.storage.index import read_index
    
    with TransactionManager(dg_dir) as tm:
        tm.begin("add", details=" ".join(args.files))
        
        index = read_index(dg_dir)
        ignore_engine = IgnoreEngine(repo_root)
        
        files_to_add: list[Path] = []
        paths_to_remove: list[str] = []
        
        is_update = getattr(args, "update", False)

        if not args.files:
            if is_update:
                args.files = ["."]
            else:
                print("Nothing specified, nothing added.\nMaybe you wanted to say 'deep add .'?", file=sys.stderr)
                raise DeepCLIException(1)

        # Pre-process for deletions when -u is used: compare index entries against arguments
        if is_update:
            for rel_path in index.entries:
                full_path = repo_root / rel_path
                if not full_path.exists():
                    # Check if this missing file is covered by any arg in args.files
                    for file_path_str in args.files:
                        p = Path(file_path_str).absolute()
                        try:
                            # Use rel_path matching
                            p_rel = p.relative_to(repo_root).as_posix()
                            if p_rel == "." or rel_path == p_rel or rel_path.startswith(f"{p_rel}/"):
                                paths_to_remove.append(rel_path)
                                break
                        except ValueError:
                            pass

        for file_path_str in args.files:
            path = Path(file_path_str).absolute()
            if not path.exists():
                # Handle explicit staging of specific deleted files
                try:
                    rel_path = path.relative_to(repo_root).as_posix()
                    rel_path, _ = sanitize_path(rel_path)
                except ValueError:
                    # Path is outside repo
                    print(f"Deep: error: {file_path_str} is outside repository", file=sys.stderr)
                    raise DeepCLIException(1)
                    
                if rel_path in index.entries:
                    if rel_path not in paths_to_remove:
                        paths_to_remove.append(rel_path)
                    continue
                else:
                    if not is_update:
                        print(f"Deep: error: {file_path_str} does not exist", file=sys.stderr)
                        raise DeepCLIException(1)
                    continue
                
            if path.is_file():
                try:
                    rel_file = path.relative_to(repo_root).as_posix()
                    rel_file, _ = sanitize_path(rel_file)
                    if is_update and rel_file not in index.entries:
                        continue
                    files_to_add.append(path)
                except ValueError:
                    pass
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
                            f_rel, _ = sanitize_path(f_rel)
                            if is_update and f_rel not in index.entries:
                                continue
                            files_to_add.append(Path(dirpath) / f)

        if paths_to_remove:
            remove_multiple_from_index(dg_dir, paths_to_remove)
            for p in paths_to_remove:
                print(f"Deep: staged deletion: {p}")

        if files_to_add:
            # Phase 1: Parallel Processing
            max_workers = min(os.cpu_count() or 4, len(files_to_add))
            
            results = []
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = []
                for file_path in files_to_add:
                    rel_path = file_path.relative_to(repo_root).as_posix()
                    
                    p_sha = None
                    p_size = None
                    p_mtime_ns = None
                    
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
                actual_results = [r for r in results if r[1] is not None]
                if actual_results:
                    for r in actual_results:
                        assert len(r[1]) == 40, f"Invalid SHA length for {r[0]}: {len(r[1])}"
                    add_multiple_to_index(dg_dir, actual_results)
                    print(f"Deep: added {len(actual_results)} files to the index.")
        
        tm.commit()
