"""
deep_git.commands.gc_cmd
~~~~~~~~~~~~~~~~~~~~~~~~
``deepgit gc`` command implementation.
"""

from __future__ import annotations

import sys
from pathlib import Path

from deep_git.core.gc import collect_garbage
from deep_git.core.repository import find_repo
from deep_git.core.utils import Color


def run(args) -> None:  # type: ignore[no-untyped-def]
    """Execute the ``gc`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    dry_run = getattr(args, "dry_run", False)
    verbose = getattr(args, "verbose", False)

    unreachable_count, total_count = collect_garbage(
        repo_root, dry_run=dry_run, verbose=verbose
    )

    if dry_run:
        print(f"Found {unreachable_count} unreachable objects (out of {total_count} total).")
        print("Run without --dry-run to quarantine them.")
    else:
        if unreachable_count > 0:
            print(f"Relocated {unreachable_count} unreachable objects to quarantine.")
        else:
            print("No unreachable objects found.")
        print(f"Done. {total_count - unreachable_count} objects remaining in database.")
