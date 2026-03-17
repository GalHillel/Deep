import time
import os
from pathlib import Path
from typing import List, Optional
from deep.core.repository import find_repo, DEEP_DIR
from deep.storage.objects import get_reachable_objects
from deep.storage.pack import PackWriter
from deep.storage.pack import PackWriter
from deep.core.refs import list_branches, list_tags, resolve_head, get_branch, get_tag

MAINTENANCE_LOG = "maintenance_log"

def run_maintenance(repo_root: Path, force: bool = False):
    """Run all maintenance tasks if needed."""
    from deep.storage import commit_graph as cg
    dg_dir = repo_root / DEEP_DIR
    if not force and not should_run_maintenance(dg_dir):
        return

    print("DeepBridge: Starting background maintenance...")
    
    # 1. Commit Graph
    print("DeepBridge: Updating commit-graph...")
    cg.build_history_graph(dg_dir)
    
    # 2. Repack if too many loose objects
    if force or count_loose_objects(dg_dir) > 100:
        print("DeepBridge: Auto-repacking loose objects...")
        repack_repository(dg_dir)
        
    # Update last run time
    update_maintenance_time(dg_dir)
    print("DeepBridge: Maintenance complete.")

def should_run_maintenance(dg_dir: Path) -> bool:
    """Check if maintenance should run (e.g. once every 24 hours)."""
    log_path = dg_dir / MAINTENANCE_LOG
    if not log_path.exists():
        return True
    
    try:
        last_run = float(log_path.read_text().strip())
        return (time.time() - last_run) > (24 * 3600)
    except (ValueError, OSError):
        return True

def update_maintenance_time(dg_dir: Path):
    (dg_dir / MAINTENANCE_LOG).write_text(str(time.time()))

def count_loose_objects(dg_dir: Path) -> int:
    from deep.storage.objects import walk_loose_shas
    objs_dir = dg_dir / "objects"
    return sum(1 for _ in walk_loose_shas(objs_dir))

def repack_repository(dg_dir: Path):
    """Repack all reachable objects and generate bitmaps."""
    objects_dir = dg_dir / "objects"
    
    # Identify all reachable SHAs
    heads = set()
    for b in list_branches(dg_dir):
        sha = get_branch(dg_dir, b)
        if sha: heads.add(sha)
    for t in list_tags(dg_dir):
        sha = get_tag(dg_dir, t)
        if sha: heads.add(sha)
    head_sha = resolve_head(dg_dir)
    if head_sha: heads.add(head_sha)
    
    if not heads:
        return
        
    reachable_shas = get_reachable_objects(objects_dir, list(heads))
    
    # Write new packfile
    pw = PackWriter(dg_dir)
    pack_sha, _ = pw.create_pack(reachable_shas)
    
    # Generate bitmaps
    from deep.storage.bitmap import generate_pack_bitmaps
    generate_pack_bitmaps(dg_dir, pack_sha)
