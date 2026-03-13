"""
deep.core.repository
~~~~~~~~~~~~~~~~~~~~

Repository initialization, discovery, and path management.

This module handles the creation of the internal ``.deep`` directory structure
and provides utilities to find the repository root from any sub-directory.
The on-disk layout is designed for DeepBridge consistency and performance.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Union

from deep.utils.utils import AtomicWriter

# Canonical repository directory name for DeepBridge.
DEEP_DIR = ".deep"
# Backward-compatible alias used throughout the existing codebase.
DEEP_GIT_DIR = DEEP_DIR


def _deep_git_path(repo_root: Path) -> Path:
    """Return the absolute path to the internal repository directory for a given root."""
    return repo_root / DEEP_GIT_DIR


def init_repo(path: Union[str, Path]) -> Path:
    """Initialize a new DeepBridge repository at the specified path.

    This creates the internal structure required for tracking history:
    - `objects/`: The content-addressable storage.
    - `refs/heads/`: Branch pointers.
    - `HEAD`: Pointer to the current active branch.
    - `index`: Staging area for upcoming commits.

    Args:
        path: Directory path where the repository should be initialized.

    Returns:
        Path: The absolute path to the internal repository directory.
    """
    repo_root = Path(path).resolve()
    dg = _deep_git_path(repo_root)

    # If the internal directory already exists, treat init as idempotent and
    # repair any missing core structures instead of failing.
    if dg.exists():
        if not dg.is_dir():
            raise FileExistsError(f"DeepBridge internal path exists but is not a directory: {dg}")
    else:
        # Create directory tree for a brand-new repository.
        (dg / "objects").mkdir(parents=True, exist_ok=True)
        (dg / "refs" / "heads").mkdir(parents=True, exist_ok=True)

    # Ensure core subdirectories always exist (self-healing for partial setups).
    (dg / "objects").mkdir(parents=True, exist_ok=True)
    (dg / "refs" / "heads").mkdir(parents=True, exist_ok=True)

    # HEAD → default branch is "main" if HEAD is missing or empty.
    head_path = dg / "HEAD"
    head_needs_init = (not head_path.exists()) or not head_path.read_text(encoding="utf-8").strip()
    if head_needs_init:
        with AtomicWriter(head_path, mode="w") as aw:
            aw.write("ref: refs/heads/main\n")

    # Empty index (binary format) if index is missing or zero-length.
    from deep.storage.index import Index
    index_path = dg / "index"
    index_needs_init = (not index_path.exists()) or index_path.stat().st_size == 0
    if index_needs_init:
        with AtomicWriter(index_path, mode="wb") as aw:
            aw.write(Index().to_binary())

    return dg


def find_repo(start: Union[str, Path] | None = None) -> Path:
    """Walk up from *start* (default: cwd) to find an internal DeepBridge directory.

    Args:
        start: Directory to begin the search from.

    Returns:
        Resolved path to the repository root (the parent of the internal directory).
    """
    current = Path(start or Path.cwd()).resolve()
    while True:
        candidate = current / DEEP_GIT_DIR
        if candidate.is_dir():
            return current
        parent = current.parent
        if parent == current:
            raise FileNotFoundError(
                "Not a DeepBridge repository (or any of the parent directories)"
            )
        current = parent
