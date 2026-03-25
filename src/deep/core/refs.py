"""
deep.core.refs
~~~~~~~~~~~~~~

Reference management: HEAD, branches, and tags.

This module provides atomic operations for reading and writing references,
resolving symbolic refs (like HEAD), and traversing the commit DAG.
All mutations are protected by secondary lockfiles to ensure concurrency
safety during high-frequency operations.
"""

from __future__ import annotations

import re
from collections import deque
from pathlib import Path
from typing import Optional

from filelock import FileLock

from deep.utils.utils import AtomicWriter

# Pattern for invalid ref name characters (control chars, backslash, etc.)
_INVALID_REF_CHARS = re.compile(r'[\x00-\x1f~^:?*\[\]\\\\]')


def _validate_ref_name(name: str) -> None:
    """Validate that a branch or tag name is safe.

    Rejects names containing path traversal patterns, control characters,
    or other dangerous sequences that could escape the refs directory.

    Raises:
        ValueError: If the name is invalid.
    """
    if not name:
        raise ValueError("Reference name cannot be empty")
    if '..' in name:
        raise ValueError(f"Reference name cannot contain '..': {name!r}")
    if name.startswith('/'):
        raise ValueError(f"Reference name cannot start with '/': {name!r}")
    if name.endswith('/'):
        raise ValueError(f"Reference name cannot end with '/': {name!r}")
    if name.endswith('.lock'):
        raise ValueError(f"Reference name cannot end with '.lock': {name!r}")
    if _INVALID_REF_CHARS.search(name):
        raise ValueError(f"Reference name contains invalid characters: {name!r}")


def is_valid_sha(s: Any) -> bool:
    """Check if s is a valid SHA-1 hex string (7-40 hex chars)."""
    if not isinstance(s, str):
        return False
    return bool(re.fullmatch(r"[0-9a-f]{7,64}", s.lower()))


# ── HEAD helpers ─────────────────────────────────────────────────────

def read_head(dg_dir: Path) -> str:
    """Read the current raw value of the HEAD reference.

    The return value is typically a symbolic reference (e.g., 'ref: refs/heads/main')
    or a raw 40-character SHA-1 hash if the repository is in a detached HEAD state.
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
        # "ref: refs/heads/feature/new" → "feature/new"
        ref_path = raw.split("ref:", 1)[1].strip()
        prefix = "refs/heads/"
        if ref_path.startswith(prefix):
            return ref_path[len(prefix):]
        return ref_path.rsplit("/", 1)[-1]
    return None


def resolve_head(dg_dir: Path) -> Optional[str]:
    """Resolve HEAD to a commit SHA-1 hex digest."""
    raw = read_head(dg_dir)
    if raw.startswith("ref:"):
        ref_path = raw.split("ref:", 1)[1].strip()
        ref_file = dg_dir / ref_path
        if not ref_file.exists():
            return None
        return ref_file.read_text(encoding="utf-8").strip()
    return raw


def resolve_revision(dg_dir: Path, revision: str) -> Optional[str]:
    """Resolve a revision string (branch, tag, sha, HEAD~n) to a SHA-1.

    Args:
        dg_dir:   Path to .deep
        revision: Revision string (e.g. "main", "v1.0", "abc1234", "HEAD~2")

    Returns:
        40-char SHA-1 hex digest, or None if not found.
    """
    if not revision:
        return None

    # Handle HEAD~n and HEAD^
    if revision.startswith("HEAD~") or revision == "HEAD^":
        if revision == "HEAD^":
            n = 1
        else:
            try:
                n = int(revision[5:])
            except ValueError:
                n = 0
        from deep.storage.objects import Commit, read_object
        current = resolve_head(dg_dir)
        for _ in range(n):
            if not current: return None
            try:
                obj = read_object(dg_dir / "objects", current)
                if isinstance(obj, Commit) and obj.parent_shas:
                    current = obj.parent_shas[0]
                else:
                    return None
            except Exception:
                return None
        return current

    if revision == "HEAD":
        return resolve_head(dg_dir)

    # Try branch
    sha = get_branch(dg_dir, revision)
    if sha: return sha

    # Try tag
    sha = get_tag(dg_dir, revision)
    if sha: return sha

    # Try full/short SHA
    if len(revision) >= 4:
        # Check if it's a valid hex
        try:
            int(revision, 16)
            # If 40 chars, assume it's a SHA
            if len(revision) == 40: return revision
            # Short SHA lookup
            objs_dir = dg_dir / "objects"
            bucket_name = revision[:2]
            bucket_dir = objs_dir / bucket_name
            
            if bucket_dir.is_dir():
                for p in bucket_dir.iterdir():
                    if p.is_file():
                        sha_candidate = bucket_name + p.name
                        if sha_candidate.startswith(revision):
                            return sha_candidate
            else:
                # Fallback if revision is < 2 chars or bucket doesn't exist
                # deep usually requires at least 4 chars for short SHA anyway.
                pass
        except ValueError:
            pass

    return None


def update_head_no_lock(dg_dir: Path, value: str) -> None:
    """Update HEAD without acquiring a lock. 
    Caller MUST hold the repository lock.
    """
    with AtomicWriter(dg_dir / "HEAD", mode="w") as aw:
        aw.write(value + "\n")


def update_head(dg_dir: Path, value: str) -> None:
    """Atomically update HEAD.

    Args:
        value: Either ``ref: refs/heads/<branch>`` for a symbolic ref, or a
               bare SHA-1 hex digest to detach HEAD.
    """
    lock = FileLock(str(dg_dir / "HEAD.lock"))
    with lock:
        update_head_no_lock(dg_dir, value)


def write_head(dg_dir: Path, ref: str) -> None:
    """Implement write_head for compatibility with commands.
    If ref is a valid branch name, writes a symbolic ref.
    Otherwise, writes the SHA directly.
    """
    # Simple check if it's a 40-char SHA
    if len(ref) == 40 and all(c in "0123456789abcdef" for c in ref.lower()):
        update_head(dg_dir, ref)
    else:
        update_head(dg_dir, f"ref: refs/heads/{ref}")



# ── Branch helpers ───────────────────────────────────────────────────

def _branch_path(dg_dir: Path, name: str) -> Path:
    return dg_dir / "refs" / "heads" / name


def _remote_ref_path(dg_dir: Path, remote: str, branch: str) -> Path:
    return dg_dir / "refs" / "remotes" / remote / branch


def get_remote_ref(dg_dir: Path, remote: str, branch: str) -> Optional[str]:
    """Return the SHA of a remote tracking branch."""
    rp = _remote_ref_path(dg_dir, remote, branch)
    if not rp.exists():
        return None
    return rp.read_text(encoding="utf-8").strip()


def update_remote_ref(dg_dir: Path, remote: str, branch: str, commit_sha: str) -> None:
    """Atomically update a remote tracking branch ref."""
    rp = _remote_ref_path(dg_dir, remote, branch)
    rp.parent.mkdir(parents=True, exist_ok=True)
    lock = FileLock(str(rp) + ".lock")
    with lock:
        with AtomicWriter(rp, mode="w") as aw:
            aw.write(commit_sha + "\n")


def find_merge_base(dg_dir: Path, sha1: str, sha2: str) -> Optional[str]:
    """Find the common ancestor of two commits (naive first-parent walk)."""
    h1 = log_history(dg_dir, sha1)
    h2 = log_history(dg_dir, sha2)
    s2 = set(h2)
    for s in h1:
        if s in s2:
            return s
    return None


def is_ancestor(objects_dir: Path, ancestor_sha: Optional[str], tip_sha: str) -> bool:
    """Return True if ancestor_sha is reachable from tip_sha."""
    if not ancestor_sha:
        return True  # Empty history is an ancestor of everything
    if ancestor_sha == tip_sha:
        return True

    from deep.storage.objects import Commit, read_object
    queue = deque([tip_sha])
    visited = {tip_sha}

    while queue:
        current = queue.popleft()
        try:
            obj = read_object(objects_dir, current)
            if not isinstance(obj, Commit):
                continue
            for p in obj.parent_shas:
                if p == ancestor_sha:
                    return True
                if p not in visited:
                    visited.add(p)
                    queue.append(p)
        except Exception:
            continue
    return False


def list_branches(dg_dir: Path) -> list[str]:
    """Return a sorted list of branch names (supports nested branches like feature/new)."""
    heads_dir = dg_dir / "refs" / "heads"
    if not heads_dir.exists():
        return []
    return sorted(
        p.relative_to(heads_dir).as_posix()
        for p in heads_dir.rglob("*")
        if p.is_file() and not p.name.endswith(".lock") and not p.name.startswith(".")
    )


def get_all_branches(dg_dir: Path) -> list[str]:
    """Helper for PR system to get all local branches."""
    return list_branches(dg_dir)


def get_branch(dg_dir: Path, name: str | None) -> Optional[str]:
    """Return the commit SHA a branch points to, or ``None`` if it doesn't exist or is invalid."""
    if name is None:
        return None
    bp = _branch_path(dg_dir, name)
    if not bp.exists():
        return None
    content = bp.read_text(encoding="utf-8").strip()
    if not is_valid_sha(content):
        return None
    return content


def update_branch_no_lock(dg_dir: Path, name: str, commit_sha: str) -> None:
    """Update a branch ref without acquiring a lock.
    Caller MUST hold the branch lock.
    """
    if not name:
        # Detached HEAD, nothing to update here
        return
    _validate_ref_name(name)
    bp = _branch_path(dg_dir, name)
    with AtomicWriter(bp, mode="w") as aw:
        aw.write(commit_sha + "\n")


def update_branch(dg_dir: Path, name: str, commit_sha: str) -> None:
    """Atomically create or update a branch ref.

    Args:
        dg_dir:     Path to ``.deep``.
        name:       Branch name (e.g. ``"main"``).
        commit_sha: 40-character SHA-1 hex digest of the tip commit.
    """
    _validate_ref_name(name)
    bp = _branch_path(dg_dir, name)
    lock = FileLock(str(bp) + ".lock")
    with lock:
        update_branch_no_lock(dg_dir, name, commit_sha)


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
    lock = FileLock(str(bp) + ".lock")
    with lock:
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
    return sorted(p.name for p in tags_dir.iterdir() if p.is_file() and not p.name.endswith(".lock"))


def get_tag(dg_dir: Path, name: str | None) -> Optional[str]:
    """Return the object SHA a tag points to, or ``None`` if it doesn't exist."""
    if name is None:
        return None
    tp = dg_dir / "refs" / "tags" / name
    if not tp.exists():
        return None
    return tp.read_text(encoding="utf-8").strip()


def create_tag(dg_dir: Path, name: str, sha: str) -> None:
    """Atomically create a tag ref.

    Args:
        dg_dir: Path to ``.deep``.
        name:   Tag name (e.g. ``"v1.0"``).
        sha:    40-character SHA-1 hex digest of the target commit or tag object.
    
    Raises:
        FileExistsError: If the tag already exists.
        ValueError: If the tag name is invalid.
    """
    _validate_ref_name(name)
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

    Returns a list of commit SHA-1 hex digests.
    By default, it follows all parents (merges) in a de-duplicated traversal.

    Args:
        dg_dir:    Path to ``.deep``.
        start_sha: Starting commit SHA (default: resolved HEAD).
        max_count: Stop after this many commits.

    Returns:
        Ordered list of commit SHA hex strings.
    """
    from deep.storage.objects import Commit, read_object  # avoid circular imports

    if start_sha is None:
        start_sha = resolve_head(dg_dir)
    if start_sha is None:
        return []

    objects_dir = dg_dir / "objects"
    result: list[str] = []
    
    # Breadth-first traversal with de-duplication
    queue = deque([start_sha])
    visited = {start_sha}

    while queue:
        if max_count is not None and len(result) >= max_count:
            break
            
        current = queue.popleft()
        result.append(current)
        
        try:
            obj = read_object(objects_dir, current)
            if isinstance(obj, Commit):
                for p in obj.parent_shas:
                    if p and p not in visited:
                        visited.add(p)
                        queue.append(p)
        except Exception:
            # Handle broken objects gracefully in log
            continue

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
    # In a full deep, log resolves the tag object back to the commit.
    # We will just map the tag SHA for now; if it's an annotated tag, 
    # the decoration naturally belongs to the tag object or we must dereference it.
    # Let's dereference it here via read_object.
    from deep.storage.objects import Tag, read_object
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
