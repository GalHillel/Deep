"""
deep.core.stash
~~~~~~~~~~~~~~~~~~~~
Stash engine for saving and popping working directory state.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Optional

from filelock import FileLock

from deep.storage.index import write_index, read_index
from deep.core.merge import three_way_merge
from deep.storage.objects import Blob, Commit, Tree, TreeEntry, read_object
from deep.core.refs import get_current_branch, resolve_head
from deep.core.repository import DEEP_GIT_DIR
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


def save_stash(repo_root: Path) -> Optional[str]:
    """Save the local modifications to a stash commit and reset the working tree.
    
    Returns the SHA of the stash commit, or None if nothing to stash.
    """
    dg_dir = repo_root / DEEP_GIT_DIR
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

    commit = Commit(
        tree_sha=tree_sha,
        parent_shas=[head_sha] if head_sha else [],
        author="DeepBridge Stash <stash@deep>",
        committer="DeepBridge Stash <stash@deep>",
        message=f"WIP on {branch_name}: {short_head}",
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
        
        from deep.storage.index import Index, IndexEntry
        new_index = Index()
        for e in head_tree.entries:
            blob = read_object(objects_dir, e.sha)
            if isinstance(blob, Blob):
                p = repo_root / e.name
                p.parent.mkdir(parents=True, exist_ok=True)
                with AtomicWriter(p, mode="wb") as aw:
                    aw.write(blob.data)
                stat = p.stat()
                new_index.entries[e.name] = IndexEntry(
                    sha=e.sha,
                    size=stat.st_size,
                    mtime=stat.st_mtime,
                )
        write_index(dg_dir, new_index)

    return commit_sha


def pop_stash(repo_root: Path) -> bool:
    """Pop the most recent stash from the stack and apply to the working tree.
    
    Returns True if successful, False if there was a conflict.
    """
    dg_dir = repo_root / DEEP_GIT_DIR
    stashes = get_stash_list(dg_dir)
    if not stashes:
        raise RuntimeError("No stash entries found.")

    stash_sha = stashes.pop()
    objects_dir = dg_dir / "objects"
    stash_commit = read_object(objects_dir, stash_sha)
    assert isinstance(stash_commit, Commit)

    # Perform a 3-way merge to working dir
    # Base = stash parent (HEAD when stash was saved)
    # Ours = current HEAD
    # Theirs = stash tree
    base_sha = stash_commit.parent_shas[0] if stash_commit.parent_shas else None
    base_tree_sha = ""
    if base_sha:
        base_commit = read_object(objects_dir, base_sha)
        assert isinstance(base_commit, Commit)
        base_tree_sha = base_commit.tree_sha

    curr_head_sha = resolve_head(dg_dir)
    curr_tree_sha = ""
    if curr_head_sha:
        curr_head_commit = read_object(objects_dir, curr_head_sha)
        assert isinstance(curr_head_commit, Commit)
        curr_tree_sha = curr_head_commit.tree_sha

    # We must ensure working dir is clean before popping!
    status = compute_status(repo_root)
    if status.staged_new or status.staged_modified or status.staged_deleted or status.modified or status.deleted:
        raise RuntimeError(
            "Error: your local changes would be overwritten by pop.\n"
            "Please commit or stash them."
        )

    merged_entries, conflicts = three_way_merge(
        objects_dir, base_tree_sha, curr_tree_sha, stash_commit.tree_sha
    )

    # Write merged entries to working tree
    from deep.storage.index import Index, IndexEntry, read_index
    
    # Clear current tracked files
    current_index = read_index(dg_dir)
    for rel_path in current_index.entries:
        full = repo_root / rel_path
        if full.exists():
            full.unlink()

    new_index = Index()
    for entry in merged_entries:
        name = entry.name
        sha = entry.sha
        if sha is None:
            continue
        blob = read_object(objects_dir, sha)
        assert isinstance(blob, Blob)
        p = repo_root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        with AtomicWriter(p, mode="wb") as aw:
            aw.write(blob.data)
        
        stat = p.stat()
        new_index.entries[name] = IndexEntry(
            sha=sha,
            size=stat.st_size,
            mtime=stat.st_mtime,
        )

    write_index(dg_dir, new_index)

    if conflicts:
        print("Stash applied with conflicts. Please resolve them.", file=sys.stderr)
        # Keep stash entry on conflict
        return False
    else:
        # Success — rewrite stash file
        sf = _stash_file(dg_dir)
        lock = FileLock(str(sf) + ".lock")
        with lock:
            with AtomicWriter(sf, mode="w") as aw:
                aw.write("\n".join(stashes) + "\n")
        print(f"Dropped refs/stash@{{0}} ({stash_sha[:7]})")
        return True
