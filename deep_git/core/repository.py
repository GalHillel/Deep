"""
deep_git.core.repository
~~~~~~~~~~~~~~~~~~~~~~~~~
Repository layout creation and discovery.

The on-disk layout mirrors Git's::

    .deep_git/
        HEAD            — contains ``ref: refs/heads/main``
        index           — staging-area file (JSON, locked)
        objects/        — content-addressable object store
        refs/
            heads/      — branch tip refs
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Union

from deep_git.core.utils import AtomicWriter

DEEP_GIT_DIR = ".deep_git"


def _deep_git_path(repo_root: Path) -> Path:
    """Return the ``.deep_git`` directory for *repo_root*."""
    return repo_root / DEEP_GIT_DIR


def init_repo(path: Union[str, Path]) -> Path:
    """Initialise a new Deep Git repository at *path*.

    Creates the directory layout::

        <path>/.deep_git/
            HEAD
            index
            objects/
            refs/heads/

    Args:
        path: Root directory for the new repository.  Will be created if it
              does not already exist.

    Returns:
        The :class:`~pathlib.Path` to the ``.deep_git`` directory.

    Raises:
        FileExistsError: If *path* already contains a ``.deep_git`` directory.
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
