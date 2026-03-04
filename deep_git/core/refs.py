"""
deep_git.core.refs
~~~~~~~~~~~~~~~~~~~
Branch references and HEAD management.

Branches are stored as plain text files under ``.deep_git/refs/heads/<name>``
containing the SHA-1 hex digest of the tip commit.

``HEAD`` is either a *symbolic ref* (``ref: refs/heads/<branch>``) pointing to
a branch, or a *detached* SHA-1 hex digest.

All writes are atomic (via :class:`~deep_git.core.utils.AtomicWriter`) and
protected by file locks to prevent concurrent corruption.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from filelock import FileLock

from deep_git.core.utils import AtomicWriter


# ── HEAD helpers ─────────────────────────────────────────────────────

def read_head(dg_dir: Path) -> str:
    """Return the raw contents of HEAD (stripped).

    This may be either ``ref: refs/heads/<branch>`` or a bare SHA-1 hex
    digest (detached HEAD).
    """
    return (dg_dir / "HEAD").read_text(encoding="utf-8").strip()


def head_is_symbolic(dg_dir: Path) -> bool:
    """Return ``True`` if HEAD is a symbolic ref, ``False`` if detached."""
    return read_head(dg_dir).startswith("ref:")


def get_current_branch(dg_dir: Path) -> Optional[str]:
    """Return the name of the current branch, or ``None`` if HEAD is detached."""
    raw = read_head(dg_dir)
    if raw.startswith("ref:"):
        # "ref: refs/heads/main" → "main"
        ref_path = raw.split("ref:", 1)[1].strip()
        return ref_path.rsplit("/", 1)[-1]
    return None


def resolve_head(dg_dir: Path) -> Optional[str]:
    """Resolve HEAD to a commit SHA-1 hex digest.

    Returns:
        The 40-character SHA-1 hex string, or ``None`` if the ref does not
        yet point to a commit (e.g. a freshly initialised repo with no
        commits).
    """
    raw = read_head(dg_dir)
    if raw.startswith("ref:"):
        ref_path = raw.split("ref:", 1)[1].strip()
        ref_file = dg_dir / ref_path
        if not ref_file.exists():
            return None
        return ref_file.read_text(encoding="utf-8").strip()
    # Detached HEAD — raw is the SHA itself.
    return raw


def update_head(dg_dir: Path, value: str) -> None:
    """Atomically update HEAD.

    Args:
        value: Either ``ref: refs/heads/<branch>`` for a symbolic ref, or a
               bare SHA-1 hex digest to detach HEAD.
    """
    lock = FileLock(str(dg_dir / "HEAD.lock"))
    with lock:
        with AtomicWriter(dg_dir / "HEAD", mode="w") as aw:
            aw.write(value + "\n")


# ── Branch helpers ───────────────────────────────────────────────────

def _branch_path(dg_dir: Path, name: str) -> Path:
    return dg_dir / "refs" / "heads" / name


def list_branches(dg_dir: Path) -> list[str]:
    """Return a sorted list of branch names."""
    heads_dir = dg_dir / "refs" / "heads"
    if not heads_dir.exists():
        return []
    return sorted(p.name for p in heads_dir.iterdir() if p.is_file())


def get_branch(dg_dir: Path, name: str) -> Optional[str]:
    """Return the commit SHA a branch points to, or ``None`` if it doesn't exist."""
    bp = _branch_path(dg_dir, name)
    if not bp.exists():
        return None
    return bp.read_text(encoding="utf-8").strip()


def update_branch(dg_dir: Path, name: str, commit_sha: str) -> None:
    """Atomically create or update a branch ref.

    Args:
        dg_dir:     Path to ``.deep_git``.
        name:       Branch name (e.g. ``"main"``).
        commit_sha: 40-character SHA-1 hex digest of the tip commit.
    """
    bp = _branch_path(dg_dir, name)
    lock = FileLock(str(bp) + ".lock")
    with lock:
        with AtomicWriter(bp, mode="w") as aw:
            aw.write(commit_sha + "\n")


def delete_branch(dg_dir: Path, name: str) -> None:
    """Delete a branch ref.

    Raises:
        FileNotFoundError: If the branch does not exist.
        ValueError: If trying to delete the current branch.
    """
    current = get_current_branch(dg_dir)
    if current == name:
        raise ValueError(f"Cannot delete the currently checked-out branch {name!r}")
    bp = _branch_path(dg_dir, name)
    if not bp.exists():
        raise FileNotFoundError(f"Branch {name!r} does not exist")
    bp.unlink()


# ── DAG traversal ───────────────────────────────────────────────────

def log_history(
    dg_dir: Path,
    start_sha: Optional[str] = None,
    max_count: Optional[int] = None,
) -> list[str]:
    """Walk the commit DAG backwards from *start_sha* (default: HEAD).

    Returns a list of commit SHA-1 hex digests from newest to oldest.
    Follows only the first parent for simplicity.

    Args:
        dg_dir:    Path to ``.deep_git``.
        start_sha: Starting commit SHA (default: resolved HEAD).
        max_count: Stop after this many commits.

    Returns:
        Ordered list of commit SHA hex strings.
    """
    from deep_git.core.objects import Commit, read_object  # avoid circular

    if start_sha is None:
        start_sha = resolve_head(dg_dir)
    if start_sha is None:
        return []

    result: list[str] = []
    current: Optional[str] = start_sha
    objects_dir = dg_dir / "objects"

    while current is not None:
        if max_count is not None and len(result) >= max_count:
            break
        result.append(current)
        obj = read_object(objects_dir, current)
        if not isinstance(obj, Commit):
            break
        current = obj.parent_shas[0] if obj.parent_shas else None

    return result
