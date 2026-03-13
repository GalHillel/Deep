"""
deep.core.gc
~~~~~~~~~~~~~~~~~
Mark-and-sweep garbage collection for DeepBridge.
"""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path
from typing import Set

from deep.storage.objects import Commit, Tree, Tag, read_object
from deep.core.refs import list_branches, get_branch, list_tags, get_tag, resolve_head
from deep.core.repository import DEEP_GIT_DIR
from deep.core.stash import get_stash_list


def mark_reachable(dg_dir: Path) -> Set[str]:
    """Return a set of SHAs reachable from all refs (branches, tags, stash, HEAD)."""
    objects_dir = dg_dir / "objects"
    reachable: Set[str] = set()
    queue: list[str] = []

    # 1. Gather all starting points (refs)
    starting_shas: Set[str] = set()
    
    # Branches
    for b in list_branches(dg_dir):
        sha = get_branch(dg_dir, b)
        if sha:
            starting_shas.add(sha)
    
    # Tags
    for t in list_tags(dg_dir):
        sha = get_tag(dg_dir, t)
        if sha:
            starting_shas.add(sha)
            
    # Stashes
    starting_shas.update(get_stash_list(dg_dir))
    
    # HEAD
    head_sha = resolve_head(dg_dir)
    if head_sha:
        starting_shas.add(head_sha)

    queue = list(starting_shas)
    
    # 2. Traverse the DAG
    while queue:
        sha = queue.pop()
        if sha in reachable:
            continue
        
        reachable.add(sha)
        
        try:
            obj = read_object(objects_dir, sha)
        except (FileNotFoundError, ValueError):
            # Missing object or corrupt - skip for GC marking
            continue

        if isinstance(obj, Commit):
            # Mark tree and ALL parents
            queue.append(obj.tree_sha)
            queue.extend(obj.parent_shas)
        elif isinstance(obj, Tree):
            # Mark all entries
            for entry in obj.entries:
                queue.append(entry.sha)
        elif isinstance(obj, Tag):
            # Mark target
            queue.append(obj.target_sha)
            
    return reachable


def collect_garbage(repo_root: Path, dry_run: bool = False, verbose: bool = False) -> tuple[int, int]:
    """Sweep unreachable objects.
    
    Returns:
        tuple (count_collected, count_total)
    """
    dg_dir = repo_root / DEEP_GIT_DIR
    objects_dir = dg_dir / "objects"
    
    if not objects_dir.exists():
        return 0, 0
    
    # Safety: Check for active WAL transactions before GC
    from deep.storage.txlog import TransactionLog
    txlog = TransactionLog(dg_dir)
    if txlog.log_path.exists() and txlog.needs_recovery():
        if verbose:
            print("DeepBridge: skipping GC — active WAL transaction detected. Run recovery first.")
        return 0, 0

    # Safety: Acquire repository lock to prevent concurrent operations during GC
    from deep.core.locks import RepositoryLock
    repo_lock = RepositoryLock(dg_dir, timeout=10.0)
    try:
        repo_lock.acquire()
    except TimeoutError:
        if verbose:
            print("DeepBridge: skipping GC — could not acquire repository lock.")
        return 0, 0
    
    # Perform Marking
    marked = mark_reachable(dg_dir)
    
    # Phase 1: Packfile Compaction
    if not dry_run and marked:
        from deep.storage.pack import PackWriter
        writer = PackWriter(dg_dir)
        pack_sha, idx_sha = writer.create_pack(list(marked))
        if verbose:
            print(f"Compacted {len(marked)} objects into pack-{pack_sha}.pack")
        
        # Now that they are packed, we can remove the loose copies
        for sha in marked:
            loose_path = objects_dir / sha[:2] / sha[2:]
            if loose_path.exists():
                loose_path.unlink()

    # Identify ALL objects on disk (remaining loose ones)
    all_shas: Set[str] = set()
    for root, dirs, files in os.walk(objects_dir):
        # Skip pack directory
        if "pack" in root:
            continue
        for f in files:
            # Expecting objects/aa/bb...
            if len(Path(root).name) == 2 and len(f) == 38:
                all_shas.add(Path(root).name + f)
    
    unreachable = all_shas - marked
    
    if not dry_run and unreachable:
        # Create quarantine dir
        timestamp = int(time.time())
        quarantine_dir = dg_dir / "quarantine" / str(timestamp)
        quarantine_dir.mkdir(parents=True, exist_ok=True)
        
        for sha in unreachable:
            src = objects_dir / sha[:2] / sha[2:]
            dst = quarantine_dir / sha
            shutil.move(src, dst)
            if verbose:
                print(f"Quarantined: {sha}")
                
        # Cleanup empty directories in objects
        for root, dirs, files in os.walk(objects_dir, topdown=False):
            if not files and not dirs:
                try:
                    os.rmdir(root)
                except OSError:
                    pass
    elif dry_run and verbose:
        for sha in unreachable:
            print(f"Would quarantine: {sha}")

    repo_lock.release()
    return len(unreachable), len(all_shas)
