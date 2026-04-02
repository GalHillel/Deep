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

from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule

def run(args) -> None:
    """Execute the ultra optimization command."""
    console = Console()
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        console.print(f"[red]Deep: error: {exc}[/red]")
        raise DeepCLIException(1)

    dg_dir = repo_root / DEEP_DIR

    console.print(Panel(
        "[bold magenta]⚓️ DEEP ULTRA MODE[/bold magenta]\n"
        "[dim]System-wide optimization in 3 stages[/dim]",
        expand=False,
        border_style="magenta"
    ))

    total_start = time.time()

    # ── Stage 1: Garbage Collection ──────────────────────────────────
    console.print(Rule("[cyan]Stage 1: Garbage Collection[/cyan]"))
    console.print("[dim]  WHY: Removes unreachable objects (orphaned blobs, trees, commits).[/dim]")
    
    try:
        from deep.core.gc import collect_garbage
        gc_start = time.time()
        removed, kept = collect_garbage(repo_root, verbose=False)
        gc_time = time.time() - gc_start
        console.print(f"  [green]✅[/green] Removed {removed} unreachable objects, kept {kept} ({gc_time:.2f}s)")
    except Exception as e:
        console.print(f"  [yellow]⚠[/yellow] GC stage skipped or failed: {e}")

    # ── Stage 2: Object Repacking ────────────────────────────────────
    console.print(Rule("[cyan]Stage 2: Object Repacking[/cyan]"))
    console.print("[dim]  WHY: Consolidates loose objects into efficient packfiles.[/dim]")

    try:
        from deep.storage.objects import walk_loose_shas
        from deep.storage.pack import PackWriter

        repack_start = time.time()
        objects_dir = dg_dir / "objects"
        loose_shas = list(walk_loose_shas(objects_dir))

        if len(loose_shas) < 5:
            console.print(f"  [dim]– Only {len(loose_shas)} loose objects, skipping repack.[/dim]")
        else:
            writer = PackWriter(dg_dir)
            pack_sha, _ = writer.create_pack(loose_shas)
            repack_time = time.time() - repack_start
            console.print(f"  [green]✅[/green] Packed {len(loose_shas)} objects into pack-{pack_sha}.pack ({repack_time:.2f}s)")
    except Exception as e:
        console.print(f"  [yellow]⚠[/yellow] Repack stage skipped or failed: {e}")

    # ── Stage 3: Commit Graph Optimization ───────────────────────────
    console.print(Rule("[cyan]Stage 3: Commit Graph Optimization[/cyan]"))
    console.print("[dim]  WHY: Accelerates history traversal with reachability indexes.[/dim]")

    try:
        from deep.storage.commit_graph import build_history_graph
        cg_start = time.time()
        num_commits = build_history_graph(dg_dir)
        cg_time = time.time() - cg_start
        console.print(f"  [green]✅[/green] Commit graph rebuilt for {num_commits} commits ({cg_time:.2f}s)")
    except Exception as e:
        console.print(f"  [yellow]⚠[/yellow] Commit graph stage skipped or failed: {e}")

    total_time = time.time() - total_start
    console.print(Rule(style="magenta"))
    console.print(f"\n[bold green]⚓️ ULTRA COMPLETE ({total_time:.2f}s)[/bold green]")

if __name__ == "__main__":
    pass
