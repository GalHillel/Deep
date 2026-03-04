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


# ── Tag helpers ──────────────────────────────────────────────────────

def _tag_path(dg_dir: Path, name: str) -> Path:
    return dg_dir / "refs" / "tags" / name


def list_tags(dg_dir: Path) -> list[str]:
    """Return a sorted list of tag names."""
    tags_dir = dg_dir / "refs" / "tags"
    if not tags_dir.exists():
        return []
    return sorted(p.name for p in tags_dir.iterdir() if p.is_file())


def get_tag(dg_dir: Path, name: str) -> Optional[str]:
    """Return the object SHA a tag points to, or ``None`` if it doesn't exist."""
    tp = _tag_path(dg_dir, name)
    if not tp.exists():
        return None
    return tp.read_text(encoding="utf-8").strip()


def create_tag(dg_dir: Path, name: str, sha: str) -> None:
    """Atomically create a tag ref.

    Args:
        dg_dir: Path to ``.deep_git``.
        name:   Tag name (e.g. ``"v1.0"``).
        sha:    40-character SHA-1 hex digest of the target commit or tag object.
    
    Raises:
        FileExistsError: If the tag already exists.
    """
    tp = _tag_path(dg_dir, name)
    if tp.exists():
        raise FileExistsError(f"Tag '{name}' already exists")
        
    lock = FileLock(str(tp) + ".lock")
    with lock:
        with AtomicWriter(tp, mode="w") as aw:
            aw.write(sha + "\n")


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


def get_commit_decorations(dg_dir: Path) -> dict[str, list[str]]:
    """Return a mapping of commit SHA to a list of decoration strings.
    E.g. { 'abcdef...': ['HEAD -> main', 'feature-x'] }
    """
    decorations: dict[str, list[str]] = {}
    
    current_branch = get_current_branch(dg_dir)
    head_sha = resolve_head(dg_dir)

    for branch_name in list_branches(dg_dir):
        sha = get_branch(dg_dir, branch_name)
        if not sha:
            continue
        
        lbl = branch_name
        if branch_name == current_branch:
            lbl = f"HEAD -> {branch_name}"
            
        decorations.setdefault(sha, []).append(lbl)

    # Note: A tag could point to a Tag object, not directly the commit.
    # In a full git, log resolves the tag object back to the commit.
    # We will just map the tag SHA for now; if it's an annotated tag, 
    # the decoration naturally belongs to the tag object or we must dereference it.
    # Let's dereference it here via read_object.
    from deep_git.core.objects import Tag, read_object
    objects_dir = dg_dir / "objects"
    for tag_name in list_tags(dg_dir):
        sha = get_tag(dg_dir, tag_name)
        if not sha:
            continue
        
        # Dereference if it's an annotated tag
        try:
            obj = read_object(objects_dir, sha)
            if isinstance(obj, Tag):
                target_sha = obj.target_sha
            else:
                target_sha = sha
            decorations.setdefault(target_sha, []).append(f"tag: {tag_name}")
        except (FileNotFoundError, ValueError):
            # Ignore broken tags
            pass

    # Detached HEAD coverage
    if not current_branch and head_sha:
        if head_sha not in decorations or not any("HEAD" in d for d in decorations[head_sha]):
            decorations.setdefault(head_sha, []).insert(0, "HEAD")

    # Sort each list to have HEAD and branches first (optional, but good for display)
    for sh, decs in decorations.items():
        # Ensure anything with HEAD comes first
        decs.sort(key=lambda x: (not x.startswith("HEAD"), x))

    return decorations
