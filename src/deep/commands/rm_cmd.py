"""
deep.commands.rm_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep rm <file>`` command implementation.

Removes a file from both the working directory and the index.
"""

from __future__ import annotations
from deep.core.errors import DeepCLIException

import sys
from pathlib import Path

from deep.storage.index import remove_multiple_from_index
from deep.core.constants import DEEP_DIR
from deep.core.repository import find_repo
from deep.storage.transaction import TransactionManager


def run(args) -> None:  # type: ignore[no-untyped-def]
    """Execute the ``rm`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Deep: error: {exc}", file=sys.stderr)
        raise DeepCLIException(1)

    dg_dir = repo_root / DEEP_DIR
    is_cached = getattr(args, "cached", False)
    is_recursive = getattr(args, "recursive", False)

    # 1. Expand paths and collect targeted tracked files
    from deep.storage.index import read_index_no_lock
    index = read_index_no_lock(dg_dir)
    
    paths_to_remove: list[str] = []
    abs_paths_to_unlink: list[Path] = []
    
    for file_path_str in args.files:
        path = Path(file_path_str).absolute()
        try:
            rel_path = path.relative_to(repo_root).as_posix()
        except ValueError:
            print(f"Deep: error: {file_path_str} is outside the repository.", file=sys.stderr)
            raise DeepCLIException(1)

        if not path.exists():
            # If path doesn't exist on disk, we can still remove it from the index if tracked
            if rel_path in index.entries:
                paths_to_remove.append(rel_path)
            else:
                print(f"Deep: error: '{rel_path}' did not match any files.", file=sys.stderr)
                raise DeepCLIException(1)
            continue

        if path.is_file():
            if rel_path not in index.entries:
                print(f"Deep: error: '{rel_path}' is not tracked.", file=sys.stderr)
                raise DeepCLIException(1)
            paths_to_remove.append(rel_path)
            if not is_cached:
                abs_paths_to_unlink.append(path)
        elif path.is_dir():
            if not is_recursive:
                print(f"Deep: error: '{rel_path}' is a directory (use -r to remove).", file=sys.stderr)
                raise DeepCLIException(1)
            
            # Find all tracked files under this directory
            prefix = f"{rel_path}/" if rel_path != "." else ""
            found_any = False
            for entry_path in index.entries:
                if entry_path == rel_path or entry_path.startswith(prefix):
                    paths_to_remove.append(entry_path)
                    if not is_cached:
                        abs_paths_to_unlink.append(repo_root / entry_path)
                    found_any = True
            
            if not found_any:
                print(f"Deep: error: '{rel_path}' did not match any tracked files.", file=sys.stderr)
                raise DeepCLIException(1)

    if not paths_to_remove:
        return

    # 2. Perform removals within a transaction
    with TransactionManager(dg_dir) as tm:
        tm.begin("rm", details=" ".join(args.files))
        
        # Batch index removal
        remove_multiple_from_index(dg_dir, list(set(paths_to_remove)))
        
        # Disk removal
        for p in set(abs_paths_to_unlink):
            if p.exists() and p.is_file():
                p.unlink()
            # Note: We don't necessarily remove empty directories here, 
            # mirroring Git behavior which mainly removes tracked files.
            
        for p in sorted(set(paths_to_remove)):
            print(f"rm '{p}'")
            
        tm.commit()
