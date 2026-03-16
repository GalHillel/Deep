"""
deep.core.status
~~~~~~~~~~~~~~~~~~~~~
Status engine — compares HEAD tree, Index, and Working Directory.

Returns structured information about which files are:
- **Staged** (in Index, different from HEAD tree)
- **Modified** (in working dir, different from Index)
- **Deleted** (in Index but missing from working dir)
- **Untracked** (in working dir but not in Index)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional, Set, Any, cast, List

from deep.core.ignore import IgnoreEngine # type: ignore
from deep.storage.index import read_index, Index # type: ignore
from deep.storage.objects import Blob, Commit, Tree, read_object # type: ignore
from deep.core.refs import resolve_head # type: ignore
from deep.core.repository import DEEP_GIT_DIR # type: ignore
from deep.utils.utils import hash_bytes # type: ignore


@dataclass
class StatusResult:
    """Structured result from the status engine."""
    staged_new: list[str] = field(default_factory=list)
    staged_modified: list[str] = field(default_factory=list)
    staged_deleted: list[str] = field(default_factory=list)
    modified: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    untracked: list[str] = field(default_factory=list)
    
    # Remote tracking metrics
    ahead_count: int = 0
    behind_count: int = 0
    remote: Optional[str] = None
    remote_branch: Optional[str] = None


def _collect_all_tree_entries(objects_dir: Path, tree_sha: str, prefix: str = "") -> Dict[str, str]:
    """Recursively collect all {rel_path: sha} entries from a tree."""
    entries = {}
    tree = read_object(objects_dir, tree_sha)
    if not isinstance(tree, Tree):
        return {}
    
    for entry in tree.entries:
        rel_path = f"{prefix}/{entry.name}" if prefix else entry.name
        if entry.mode == "40000": # Directory
            entries.update(_collect_all_tree_entries(objects_dir, entry.sha, rel_path))
        else:
            entries[rel_path] = entry.sha
    return entries


def _get_head_tree_entries(dg_dir: Path) -> Dict[str, str]:
    """Return a dict mapping ``{name: blob_sha}`` from the HEAD commit's tree (recursive)."""
    head_sha = resolve_head(dg_dir)
    if head_sha is None:
        return {}
    objects_dir = dg_dir / "objects"
    commit = read_object(objects_dir, head_sha)
    if not isinstance(commit, Commit):
        return {}
    return _collect_all_tree_entries(objects_dir, commit.tree_sha)


def _walk_working_dir(repo_root: Path) -> Set[str]:
    """Return a set of relative POSIX paths for every file in the working tree.

    Skips the ``.deep_git`` directory.
    """
    files: set[str] = set()
    for dirpath, dirnames, filenames in os.walk(repo_root):
        # Skip .deep_git and hidden dirs.
        dirnames[:] = [ # type: ignore
            d for d in dirnames
            if d != DEEP_GIT_DIR and not d.startswith(".")
        ]
        for fname in filenames:
            if fname.startswith("."):
                continue
            full = Path(dirpath) / fname
            rel = full.relative_to(repo_root).as_posix()
            files.add(rel)
    return files


def _blob_sha_for_file(file_path: Path) -> str:
    """Compute the blob SHA for a file's current on-disk content."""
    data = file_path.read_bytes()
    blob = Blob(data=data)
    return blob.sha


from concurrent.futures import ThreadPoolExecutor

def _check_file_status(repo_root: Path, path: str, index_sha: str, index_mtime: float, index_size: int) -> tuple[str, bool]:
    """Check if a file is modified. Returns (path, is_modified)."""
    full_path = repo_root / path
    if not full_path.exists():
        return path, True 
        
    try:
        stat = full_path.stat()
        # Optimization: Skip hashing if mtime and size haven't changed
        if stat.st_mtime == index_mtime and stat.st_size == index_size:
            return path, False
        
        # Hash check
        wd_sha = _blob_sha_for_file(full_path)
        return path, wd_sha != index_sha
    except (FileNotFoundError, PermissionError):
        return path, True


def compute_status(repo_root: Path, index: Optional[Index] = None) -> StatusResult:
    """Compute the full repository status concurrently.
    
    If *index* is provided, it is used directly without further locking.
    Otherwise, the index is read from disk with an exclusive lock.
    """
    dg_dir = repo_root / DEEP_GIT_DIR
    result = StatusResult()

    # 1. HEAD tree
    head_entries = _get_head_tree_entries(dg_dir)

    # 2. Index
    if index is None:
        index = read_index(dg_dir)
    
    # 3. Working dir
    working_files = _walk_working_dir(repo_root)

    all_paths = set(head_entries) | set(index.entries.keys()) | working_files
    ignore_engine = IgnoreEngine(repo_root)

    # Prepare parallel checks for Unstaged changes (Working dir vs Index)
    to_check = []
    for path in all_paths:
        if path in index.entries and path in working_files:
            entry = index.entries[path]
            to_check.append((path, entry.sha, entry.mtime, entry.size))

    modified_paths = set()
    if to_check:
        max_workers = min(os.cpu_count() or 4, len(to_check))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [cast(Any, executor).submit(_check_file_status, repo_root, *args) for args in to_check] # type: ignore
            for f in futures:
                path, is_mod = f.result()
                if is_mod:
                    modified_paths.add(path)

    for path in sorted(all_paths):
        in_head = path in head_entries
        in_index = path in index.entries
        in_wd = path in working_files

        # --- Staged changes (Index vs HEAD) ---
        if in_index and not in_head:
            result.staged_new.append(path)
        elif in_index and in_head and index.entries[path].sha != head_entries[path]:
            result.staged_modified.append(path)
        elif not in_index and in_head:
            result.staged_deleted.append(path)

        # --- Unstaged changes (Working dir vs Index) ---
        if in_index and in_wd:
            if path in modified_paths:
                result.modified.append(path)
        elif in_index and not in_wd:
            result.deleted.append(path)

        # --- Untracked ---
        if in_wd and not in_index:
            if not ignore_engine.is_ignored(path):
                result.untracked.append(path)

    # 4. Ahead/Behind metrics
    from deep.core.config import Config # type: ignore
    from deep.core.refs import get_current_branch, get_remote_ref, find_merge_base, log_history # type: ignore
    
    branch = get_current_branch(dg_dir)
    if branch:
        config = Config(repo_root)
        remote = config.get(f"branch.{branch}.remote")
        merge_ref = config.get(f"branch.{branch}.merge") # e.g. refs/heads/main
        
        if remote and merge_ref:
            remote_branch = merge_ref.rsplit("/", 1)[-1]
            remote_sha = get_remote_ref(dg_dir, remote, remote_branch)
            local_sha = resolve_head(dg_dir)
            
            if local_sha and remote_sha:
                result.remote = remote
                result.remote_branch = remote_branch
                
                if local_sha == remote_sha:
                    result.ahead_count = 0
                    result.behind_count = 0
                else:
                    base = find_merge_base(dg_dir, local_sha, remote_sha)
                    if base:
                        # Ahead = count(base..local)
                        ahead = log_history(dg_dir, local_sha)
                        try:
                            idx = ahead.index(base)
                            result.ahead_count = idx
                        except ValueError:
                            pass # Should not happen if base is ancestor
                            
                        # Behind = count(base..remote)
                        # We would need the remote's history objects to be exact, 
                        # but we can estimate or use what we have in objects/
                        behind = log_history(dg_dir, remote_sha)
                        try:
                            idx = behind.index(base)
                            result.behind_count = idx
                        except ValueError:
                            pass

    return result
