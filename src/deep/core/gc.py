"""
deep.core.gc
~~~~~~~~~~~~~~~~~
Mark-and-sweep garbage collection for Deep.
"""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path
from typing import Set

from deep.storage.objects import Commit, Tree, Tag, read_object
from deep.core.refs import list_branches, get_branch, list_tags, get_tag, resolve_head
from deep.core.constants import DEEP_DIR
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
    if head_sha and len(head_sha) == 40:
        starting_shas.add(head_sha)

    # Filter all starting SHAs for 40-char length to avoid corrupt/lock content
    queue = [s for s in starting_shas if len(s) == 40]
    
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


def collect_garbage(repo_root: Path, dry_run: bool = False, verbose: bool = False, prune_expire: int = 3600) -> tuple[int, int]:
    """Sweep unreachable objects.
    
    Args:
        repo_root: Path to repository.
        dry_run: If True, only report what would be done.
        verbose: Print detailed progress.
        prune_expire: Only prune unreachable objects older than this (seconds). Default 1h.
        
    Returns:
        tuple (count_collected, count_total)
    """
    dg_dir = repo_root / DEEP_DIR
    objects_dir = dg_dir / "objects"
    
    if not objects_dir.exists():
        return 0, 0
    
    # Safety: Acquire repository lock to prevent concurrent operations during GC
    from deep.core.locks import RepositoryLock
    repo_lock = RepositoryLock(dg_dir, timeout=15.0)
    try:
        repo_lock.acquire()
    except TimeoutError:
        if verbose:
            print("Deep: skipping GC — could not acquire repository lock.")
        return 0, 0
    
    # Safety: Check for active WAL transactions BEFORE this process started.
    # If we are running inside a TransactionManager, we expect ONE incomplete 
    # transaction (ours). If there are more, they are stale/crashed.
    from deep.storage.txlog import TransactionLog
    txlog = TransactionLog(dg_dir)
    incomplete = txlog.get_incomplete()
    
    # If more than 1 incomplete, or 1 and it's not very recent, require recovery.
    if len(incomplete) > 1 or (len(incomplete) == 1 and time.time() - incomplete[0].timestamp > 60):
        if verbose:
            print(f"Deep: skipping GC — {len(incomplete)} stale transactions detected. Run recovery first.")
        repo_lock.release()
        return 0, 0
    
    # Identify ALL loose objects on disk BEFORE packing/unlinking
    from deep.storage.objects import walk_loose_shas
    all_loose_shas = set(walk_loose_shas(objects_dir))

    # Perform Marking
    marked = mark_reachable(dg_dir)
    
    # Phase 1: Packfile Compaction
    if not dry_run and marked:
        from deep.storage.pack import PackWriter
        writer = PackWriter(dg_dir)
        # Identify existing packs before creating a new one
        existing_packs = list(writer.pack_dir.glob("pack-*.pack")) + list(writer.pack_dir.glob("pack-*.idx"))
        
        pack_sha, idx_sha = writer.create_pack(list(marked))
        if verbose:
            print(f"Compacted {len(marked)} objects into pack-{pack_sha}.pack")
        
        # Now that they are packed, we can remove the loose copies
        from deep.storage.objects import _object_path
        for sha in marked:
            loose_path = _object_path(objects_dir, sha)
            if loose_path.exists():
                loose_path.unlink()
        
        # Delete old packfiles that were not just created
        new_pack_base = f"pack-{pack_sha}"
        for p in existing_packs:
            if p.stem != new_pack_base:
                try:
                    p.unlink()
                    if verbose:
                        print(f"Removed old pack file: {p.name}")
                except OSError:
                    pass

    unreachable = all_loose_shas - marked
    
    if not dry_run and unreachable:
        # Create quarantine dir
        timestamp = int(time.time())
        quarantine_dir = dg_dir / "quarantine" / str(timestamp)
        quarantine_dir.mkdir(parents=True, exist_ok=True)
        
        from deep.storage.objects import _object_path
        now = time.time()
        for sha in unreachable:
            src = _object_path(objects_dir, sha, level=2)
            if not src.exists():
                src = _object_path(objects_dir, sha, level=1)
                
            if src.exists():
                # Age threshold check
                try:
                    mtime = os.path.getmtime(src)
                    age = now - mtime
                    if age < prune_expire:
                        if verbose:
                            print(f"Skipping recently created object: {sha} (age: {age:.1f}s, threshold: {prune_expire}s)")
                        continue
                except OSError:
                    continue

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

    # Prune old quarantine directories (> 14 days)
    if not dry_run:
        quarantine_base = dg_dir / "quarantine"
        if quarantine_base.exists():
            now = time.time()
            prune_thresh = 14 * 24 * 3600
            for qdir in quarantine_base.iterdir():
                if qdir.is_dir():
                    try:
                        q_time = int(qdir.name)
                        if now - q_time > prune_thresh:
                            shutil.rmtree(qdir)
                            if verbose:
                                print(f"Pruned old quarantine: {qdir.name}")
                    except ValueError:
                        pass

    repo_lock.release()
    # Total count = objects that were loose initially.
    # We don't delve into existing packs for the 'count_total' in this simple GC.
    return len(unreachable), len(all_loose_shas)
