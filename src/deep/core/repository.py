"""
deep.core.repository
~~~~~~~~~~~~~~~~~~~~

Repository initialization, discovery, and path management.

This module handles the creation of the `.deep_git` directory structure 
and provides utilities to find the repository root from any sub-directory.
The on-disk layout is designed for Git compatibility and performance.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Union

from deep.utils.utils import AtomicWriter

DEEP_GIT_DIR = ".deep_git"


def _deep_git_path(repo_root: Path) -> Path:
    """Return the absolute path to the `.deep_git` directory for a given root."""
    return repo_root / DEEP_GIT_DIR


def init_repo(path: Union[str, Path]) -> Path:
    """Initialize a new Deep VCS repository at the specified path.

    This creates the internal structure required for tracking history:
    - `objects/`: The content-addressable storage.
    - `refs/heads/`: Branch pointers.
    - `HEAD`: Pointer to the current active branch.
    - `index`: Staging area for upcoming commits.

    Args:
        path: Directory path where the repository should be initialized.

    Returns:
        Path: The absolute path to the newly created `.deep_git` directory.

    Raises:
        FileExistsError: If a repository already exists in the target path.
    """
    repo_root = Path(path).resolve()
    dg = _deep_git_path(repo_root)

    if dg.exists():
        raise FileExistsError(f"Repository already exists at {dg}")

    # Create directory tree.
    (dg / "objects").mkdir(parents=True, exist_ok=True)
    (dg / "refs" / "heads").mkdir(parents=True, exist_ok=True)

    # HEAD → default branch is "main".
    with AtomicWriter(dg / "HEAD", mode="w") as aw:
        aw.write("ref: refs/heads/main\n")

    # Empty index (JSON object).
    with AtomicWriter(dg / "index", mode="w") as aw:
        aw.write(json.dumps({"entries": {}}) + "\n")

    return dg


def find_repo(start: Union[str, Path] | None = None) -> Path:
    """Walk up from *start* (default: cwd) to find a ``.deep_git`` directory.

    Args:
        start: Directory to begin the search from.

    Returns:
        Resolved path to the repository root (the parent of ``.deep_git``).

    Raises:
        FileNotFoundError: If no ``.deep_git`` directory is found.
    """
    current = Path(start or Path.cwd()).resolve()
    while True:
        candidate = current / DEEP_GIT_DIR
        if candidate.is_dir():
            return current
        parent = current.parent
        if parent == current:
            raise FileNotFoundError(
                "Not a Deep Git repository (or any of the parent directories)"
            )
        current = parent
