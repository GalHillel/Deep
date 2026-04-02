"""
deep.commands.gc_cmd
~~~~~~~~~~~~~~~~~~~~~~~~
``deep gc`` command implementation.
"""

from __future__ import annotations
from deep.core.errors import DeepCLIException

import sys
from pathlib import Path

from deep.core.gc import collect_garbage
from deep.core.repository import find_repo
from deep.utils.ux import Color


def run(args) -> None:  # type: ignore[no-untyped-def]
    """Execute the ``gc`` command."""
    from deep.storage.transaction import TransactionManager
    from deep.core.constants import DEEP_DIR

    from rich.console import Console

    console = Console()
    try:
        repo_root = find_repo()
        dg_dir = repo_root / DEEP_DIR
    except FileNotFoundError as exc:
        console.print(f"[red]Deep: error: {exc}[/red]")
        raise DeepCLIException(1)

    dry_run = getattr(args, "dry_run", False)
    verbose = getattr(args, "verbose", False)
    prune_expire = getattr(args, "prune", 3600)

    with TransactionManager(dg_dir) as tm:
        tm.begin("gc")
        unreachable_count, total_count = collect_garbage(
            repo_root, dry_run=dry_run, verbose=verbose, prune_expire=prune_expire
        )
        tm.commit()

    if dry_run:
        console.print(f"\n[bold blue]⚓️ Cleanup summary (dry-run):[/bold blue]")
        console.print(f"  Unreachable objects that would be pruned: [yellow]{unreachable_count}[/yellow]")
        console.print(f"  Total objects in database: {total_count}")
        console.print(f"\nRun without [bold]--dry-run[/bold] to relocate them to quarantine.")
    else:
        console.print(f"\n[bold green]⚓️ Garbage collection complete.[/bold green]")
        if unreachable_count > 0:
            console.print(f"  Relocated [yellow]{unreachable_count}[/yellow] unreachable objects to quarantine.")
        else:
            console.print("  No unreachable objects required pruning.")
        console.print(f"  Database optimized. [bold]{total_count - unreachable_count}[/bold] objects remaining.")
