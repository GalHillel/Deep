"""
deep.core.stash
~~~~~~~~~~~~~~~~~~~~
Stash engine for saving and popping working directory state.
"""

from __future__ import annotations

import sys
import time
import hashlib
from pathlib import Path
from typing import Optional

from filelock import FileLock

from deep.storage.index import write_index, read_index
from deep.core.merge import three_way_merge
from deep.storage.objects import Blob, Commit, Tree, TreeEntry, read_object
from deep.core.refs import get_current_branch, resolve_head
from deep.core.constants import DEEP_DIR
from deep.core.status import _get_head_tree_entries, compute_status
from deep.utils.utils import AtomicWriter


def _stash_file(dg_dir: Path) -> Path:
    return dg_dir / "refs" / "stash"


def get_stash_list(dg_dir: Path) -> list[str]:
    """Return a list of stash commit SHAs, oldest first. The last element is the newest stash."""
    sf = _stash_file(dg_dir)
    if not sf.exists():
        return []
    lines = sf.read_text(encoding="utf-8").strip().splitlines()
    return [ln.strip() for ln in lines if ln.strip()]


def save_stash(repo_root: Path, message: Optional[str] = None) -> Optional[str]:
    """Save the local modifications to a stash commit and reset the working tree.
    
    Returns the SHA of the stash commit, or None if nothing to stash.
    """
    dg_dir = repo_root / DEEP_DIR
    objects_dir = dg_dir / "objects"
    status = compute_status(repo_root)

    # Tracked files with modifications
    active_files = (
        status.staged_new + status.staged_modified + status.staged_deleted +
        status.modified + status.deleted
    )

    if not active_files:
        return None

    # Original head tree entries
    tree_entries_dict = _get_head_tree_entries(dg_dir)

    # Apply deletions
    for f in status.staged_deleted + status.deleted:
        tree_entries_dict.pop(f, None)

    # Apply additions / modifications
    for f in status.staged_new + status.staged_modified + status.modified:
        f_path = repo_root / f
        data = f_path.read_bytes()
        blob = Blob(data=data)
        blob_sha = blob.write(objects_dir)
        tree_entries_dict[f] = blob_sha

    # Build new tree
    entries = [TreeEntry(mode="100644", name=name, sha=sha) for name, sha in tree_entries_dict.items()]
    tree = Tree(entries=entries)
    tree_sha = tree.write(objects_dir)

    head_sha = resolve_head(dg_dir)
    branch_name = get_current_branch(dg_dir) or "(detached HEAD)"
    short_head = head_sha[:7] if head_sha else "empty"

    default_msg = f"WIP on {branch_name}: {short_head}"
    final_msg = f"{message}" if message else default_msg

    commit = Commit(
        tree_sha=tree_sha,
        parent_shas=[head_sha] if head_sha else [],
        author="Deep Stash <stash@deep>",
        committer="Deep Stash <stash@deep>",
        message=final_msg,
        timestamp=int(time.time()),
    )
    commit_sha = commit.write(objects_dir)

    # Push to stash stack
    sf = _stash_file(dg_dir)
    sf.parent.mkdir(parents=True, exist_ok=True)
    lock = FileLock(str(sf) + ".lock")
    with lock:
        current_stashes = get_stash_list(dg_dir)
        current_stashes.append(commit_sha)
        with AtomicWriter(sf, mode="w") as aw:
            aw.write("\n".join(current_stashes) + "\n")

    # Reset working tree (equivalent to `reset --hard HEAD`)
    index = read_index(dg_dir)
    
    # Remove tracked files from WD
    for rel_path in index.entries:
        p = repo_root / rel_path
        if p.exists():
            p.unlink()

    if head_sha:
        head_commit = read_object(objects_dir, head_sha)
        assert isinstance(head_commit, Commit)
        head_tree = read_object(objects_dir, head_commit.tree_sha)
        assert isinstance(head_tree, Tree)
        
        from deep.storage.index import DeepIndex, DeepIndexEntry
        new_index = DeepIndex()
        for e in head_tree.entries:
            blob = read_object(objects_dir, e.sha)
            if isinstance(blob, Blob):
                p = repo_root / e.name
                p.parent.mkdir(parents=True, exist_ok=True)
                with AtomicWriter(p, mode="wb") as aw:
                    aw.write(blob.data)
                stat = p.stat()
                import struct
                new_index.entries[e.name] = DeepIndexEntry(
                    path_hash=struct.unpack(">Q", hashlib.sha256(e.name.encode()).digest()[:8])[0],
                    content_hash=e.sha,
                    mtime_ns=stat.st_mtime_ns,
                    size=stat.st_size,
                )
        write_index(dg_dir, new_index)

    return commit_sha


def _apply_stash_to_wd(repo_root: Path, stash_sha: str) -> bool:
    """Helper to apply a specific stash SHA to the working tree.
    Does NOT remove it from the refs/stash file.
    """
    dg_dir = repo_root / DEEP_DIR
    objects_dir = dg_dir / "objects"
    stash_commit = read_object(objects_dir, stash_sha)
    assert isinstance(stash_commit, Commit)

    # Perform a 3-way merge to working dir
    base_sha = stash_commit.parent_shas[0] if stash_commit.parent_shas else None
    base_tree_sha = ""
    if base_sha:
        try:
            base_commit = read_object(objects_dir, base_sha)
            if isinstance(base_commit, Commit):
                base_tree_sha = base_commit.tree_sha
        except (FileNotFoundError, ValueError):
            pass

    curr_head_sha = resolve_head(dg_dir)
    curr_tree_sha = ""
    if curr_head_sha:
        curr_head_commit = read_object(objects_dir, curr_head_sha)
        assert isinstance(curr_head_commit, Commit)
        curr_tree_sha = curr_head_commit.tree_sha

    # Ensure working dir is clean before apply
    status = compute_status(repo_root)
    if status.staged_new or status.staged_modified or status.staged_deleted or status.modified or status.deleted:
        raise RuntimeError(
            "Error: your local changes would be overwritten by apply.\n"
            "Please commit or stash them before applying."
        )

    merged_tree_sha, conflicts = three_way_merge(
        objects_dir, base_tree_sha, curr_tree_sha, stash_commit.tree_sha
    )

    # Write merged entries to working tree
    from deep.storage.index import DeepIndex, DeepIndexEntry, read_index
    
    # Clear current tracked files
    current_index = read_index(dg_dir)
    for rel_path in current_index.entries:
        full = repo_root / rel_path
        if full.exists() and full.is_file():
            full.unlink()

    # Apply merged tree
    merged_tree = read_object(objects_dir, merged_tree_sha)
    assert isinstance(merged_tree, Tree)

    new_index = DeepIndex()
    
    def _flatten_tree(tree_sha: str, prefix: str = ""):
        t = read_object(objects_dir, tree_sha)
        assert isinstance(t, Tree)
        for entry in t.entries:
            full_name = f"{prefix}/{entry.name}" if prefix else entry.name
            if entry.mode == "40000": # dir
                _flatten_tree(entry.sha, full_name)
            else:
                obj = read_object(objects_dir, entry.sha)
                if isinstance(obj, Blob):
                    p = repo_root / full_name
                    p.parent.mkdir(parents=True, exist_ok=True)
                    with AtomicWriter(p, mode="wb") as aw:
                        aw.write(obj.data)
                    stat = p.stat()
                    import struct
                    new_index.entries[full_name] = DeepIndexEntry(
                        path_hash=struct.unpack(">Q", hashlib.sha256(full_name.encode()).digest()[:8])[0],
                        content_hash=entry.sha,
                        mtime_ns=stat.st_mtime_ns,
                        size=stat.st_size,
                    )
    
    _flatten_tree(merged_tree_sha)
    write_index(dg_dir, new_index)

    if conflicts:
        print("Stash applied with conflicts. Please resolve them.", file=sys.stderr)
        return False
    return True


def apply_stash(repo_root: Path, index: int = 0) -> bool:
    """Apply a specific stash by index without removing it from the stack."""
    dg_dir = repo_root / DEEP_DIR
    stashes = get_stash_list(dg_dir)
    if not stashes:
        raise RuntimeError("No stash entries found.")
    
    # newest is at the end of the list, index 0 is newest in Git commands
    idx = len(stashes) - 1 - index
    if idx < 0 or idx >= len(stashes):
        raise RuntimeError(f"Index {index} is out of range for stash stack.")
    
    stash_sha = stashes[idx]
    return _apply_stash_to_wd(repo_root, stash_sha)


def pop_stash(repo_root: Path) -> bool:
    """Pop the most recent stash from the stack and apply to the working tree."""
    dg_dir = repo_root / DEEP_DIR
    stashes = get_stash_list(dg_dir)
    if not stashes:
        raise RuntimeError("No stash entries found.")

    stash_sha = stashes[-1]
    success = _apply_stash_to_wd(repo_root, stash_sha)
    
    if success:
        stashes.pop()
        sf = _stash_file(dg_dir)
        lock = FileLock(str(sf) + ".lock")
        with lock:
            with AtomicWriter(sf, mode="w") as aw:
                aw.write("\n".join(stashes) + "\n")
        print(f"Dropped refs/stash@{{0}} ({stash_sha[:7]})")
        return True
    return False


def drop_stash(repo_root: Path, index: int = 0) -> None:
    """Remove a specific stash from the stack."""
    dg_dir = repo_root / DEEP_DIR
    stashes = get_stash_list(dg_dir)
    if not stashes:
        raise RuntimeError("No stash entries found.")
    
    idx = len(stashes) - 1 - index
    if idx < 0 or idx >= len(stashes):
        raise RuntimeError(f"Index {index} is out of range for stash stack.")
    
    dropped_sha = stashes.pop(idx)
    sf = _stash_file(dg_dir)
    lock = FileLock(str(sf) + ".lock")
    with lock:
        with AtomicWriter(sf, mode="w") as aw:
            aw.write("\n".join(stashes) + "\n")
    print(f"Dropped refs/stash@{{{index}}} ({dropped_sha[:7]})")


def clear_stash(repo_root: Path) -> None:
    """Delete all stashes."""
    dg_dir = repo_root / DEEP_DIR
    sf = _stash_file(dg_dir)
    if sf.exists():
        lock = FileLock(str(sf) + ".lock")
        with lock:
            sf.unlink()
    print("Stash cleared.")
