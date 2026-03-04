"""
deep_git.core.status
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
from typing import Dict, Optional, Set

from deep_git.core.index import read_index
from deep_git.core.objects import Blob, Commit, Tree, read_object
from deep_git.core.refs import resolve_head
from deep_git.core.repository import DEEP_GIT_DIR
from deep_git.core.utils import hash_bytes


@dataclass
class StatusResult:
    """Structured result from the status engine."""
    staged_new: list[str] = field(default_factory=list)
    staged_modified: list[str] = field(default_factory=list)
    staged_deleted: list[str] = field(default_factory=list)
    modified: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    untracked: list[str] = field(default_factory=list)


def _get_head_tree_entries(dg_dir: Path) -> Dict[str, str]:
    """Return a dict mapping ``{name: blob_sha}`` from the HEAD commit's tree.

    Returns an empty dict if there are no commits yet.
    """
    head_sha = resolve_head(dg_dir)
    if head_sha is None:
        return {}
    objects_dir = dg_dir / "objects"
    commit = read_object(objects_dir, head_sha)
    if not isinstance(commit, Commit):
        return {}
    tree = read_object(objects_dir, commit.tree_sha)
    if not isinstance(tree, Tree):
        return {}
    return {entry.name: entry.sha for entry in tree.entries}


def _walk_working_dir(repo_root: Path) -> Set[str]:
    """Return a set of relative POSIX paths for every file in the working tree.

    Skips the ``.deep_git`` directory.
    """
    files: set[str] = set()
    for dirpath, dirnames, filenames in os.walk(repo_root):
        # Skip .deep_git and hidden dirs.
        dirnames[:] = [
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


def compute_status(repo_root: Path) -> StatusResult:
    """Compute the full repository status.

    Compares three states:
    1. HEAD commit's tree  (``head_entries``)
    2. Index / staging area (``index_entries``)
    3. Working directory    (``working_files``)

    Args:
        repo_root: Repository root directory.

    Returns:
        A :class:`StatusResult` with categorised file lists.
    """
    dg_dir = repo_root / DEEP_GIT_DIR
    result = StatusResult()

    # 1. HEAD tree
    head_entries = _get_head_tree_entries(dg_dir)

    # 2. Index
    index = read_index(dg_dir)
    index_entries = {path: entry.sha for path, entry in index.entries.items()}

    # 3. Working dir
    working_files = _walk_working_dir(repo_root)

    all_paths = set(head_entries) | set(index_entries) | working_files

    for path in sorted(all_paths):
        in_head = path in head_entries
        in_index = path in index_entries
        in_wd = path in working_files

        # --- Staged changes (Index vs HEAD) ---
        if in_index and not in_head:
            result.staged_new.append(path)
        elif in_index and in_head and index_entries[path] != head_entries[path]:
            result.staged_modified.append(path)
        elif not in_index and in_head:
            result.staged_deleted.append(path)

        # --- Unstaged changes (Working dir vs Index) ---
        if in_index and in_wd:
            wd_sha = _blob_sha_for_file(repo_root / path)
            if wd_sha != index_entries[path]:
                result.modified.append(path)
        elif in_index and not in_wd:
            result.deleted.append(path)

        # --- Untracked ---
        if in_wd and not in_index:
            result.untracked.append(path)

    return result
