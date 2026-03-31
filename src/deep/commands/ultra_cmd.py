"""
deep.commands.ultra_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep ultra`` command implementation.

ULTRA Mode: Executes real system optimization in 3 stages:
  1. Garbage Collection — remove unreachable objects
  2. Object Repacking — consolidate loose objects into packfiles
  3. Commit Graph Optimization — rebuild commit-graph index
"""

from __future__ import annotations
from deep.core.errors import DeepCLIException

import sys
import time
from pathlib import Path

from deep.core.constants import DEEP_DIR
from deep.core.repository import find_repo
from deep.utils.ux import DeepHelpFormatter, format_example
from typing import Any


def setup_parser(subparsers: Any) -> None:
    """Set up the 'ultra' command parser."""
    subparsers.add_parser(
        "ultra",
        help="Run comprehensive repository optimization",
        description="Execute a multi-stage system optimization including garbage collection, object repacking, and commit-graph rebuilding.",
        epilog=f"""
Examples:
{format_example("deep ultra", "Run all optimization stages")}
""",
        formatter_class=DeepHelpFormatter,
    )


def run(args) -> None:
    """Execute the ultra optimization command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Deep: error: {exc}", file=sys.stderr)
        raise DeepCLIException(1)

    dg_dir = repo_root / DEEP_DIR

    print(Color.wrap(Color.BOLD + Color.MAGENTA, "═══ DEEP ULTRA MODE ═══"))
    print(Color.wrap(Color.DIM, "System-wide optimization in 3 stages\n"))

    total_start = time.time()

    # ── Stage 1: Garbage Collection ──────────────────────────────────
    print(Color.wrap(Color.CYAN, "▶ Stage 1: Garbage Collection"))
    print(Color.wrap(Color.DIM, "  WHY: Removes unreachable objects (orphaned blobs, trees, commits)"))
    print(Color.wrap(Color.DIM, "       that are no longer referenced by any branch, tag, or stash."))
    print(Color.wrap(Color.DIM, "  WHAT: Walks all refs to find reachable objects, then deletes the rest.\n"))

    try:
        from deep.core.gc import collect_garbage
        gc_start = time.time()
        removed, kept = collect_garbage(repo_root, verbose=True)
        gc_time = time.time() - gc_start
        print(f"  {Color.wrap(Color.GREEN, '✓')} Removed {removed} unreachable objects, kept {kept} ({gc_time:.2f}s)\n")
    except Exception as e:
        print(f"  {Color.wrap(Color.YELLOW, '⚠')} GC skipped: {e}\n")

    # ── Stage 2: Object Repacking ────────────────────────────────────
    print(Color.wrap(Color.CYAN, "▶ Stage 2: Object Repacking"))
    print(Color.wrap(Color.DIM, "  WHY: Loose objects on disk are individually stored and slow to access."))
    print(Color.wrap(Color.DIM, "       Packing consolidates them into efficient packfiles with delta compression."))
    print(Color.wrap(Color.DIM, "  WHAT: Collects all loose objects, builds a packfile, removes originals.\n"))

    try:
        from deep.storage.objects import walk_loose_shas
        from deep.storage.pack import PackWriter

        repack_start = time.time()
        objects_dir = dg_dir / "objects"
        loose_shas = list(walk_loose_shas(objects_dir))

        if len(loose_shas) < 5:
            print(f"  {Color.wrap(Color.DIM, '–')} Only {len(loose_shas)} loose objects, skipping repack.\n")
        else:
            writer = PackWriter(dg_dir)
            pack_sha, _ = writer.create_pack(loose_shas)
            repack_time = time.time() - repack_start
            print(f"  {Color.wrap(Color.GREEN, '✓')} Packed {len(loose_shas)} objects into pack-{pack_sha}.pack ({repack_time:.2f}s)\n")
    except Exception as e:
        print(f"  {Color.wrap(Color.YELLOW, '⚠')} Repack skipped: {e}\n")

    # ── Stage 3: Commit Graph Optimization ───────────────────────────
    print(Color.wrap(Color.CYAN, "▶ Stage 3: Commit Graph Optimization"))
    print(Color.wrap(Color.DIM, "  WHY: The commit-graph index accelerates history traversal by storing"))
    print(Color.wrap(Color.DIM, "       pre-computed parent pointers and generation numbers."))
    print(Color.wrap(Color.DIM, "  WHAT: Walks all commits, builds a binary index for fast lookups.\n"))

    try:
        from deep.storage.commit_graph import build_history_graph
        cg_start = time.time()
        num_commits = build_history_graph(dg_dir)
        cg_time = time.time() - cg_start
        print(f"  {Color.wrap(Color.GREEN, '✓')} Commit graph rebuilt for {num_commits} commits ({cg_time:.2f}s)\n")
    except Exception as e:
        print(f"  {Color.wrap(Color.YELLOW, '⚠')} Commit graph skipped: {e}\n")

    total_time = time.time() - total_start
    print(Color.wrap(Color.BOLD + Color.GREEN, f"═══ ULTRA COMPLETE ({total_time:.2f}s) ═══"))
