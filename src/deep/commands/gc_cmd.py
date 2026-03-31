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
from deep.utils.ux import (
    DeepHelpFormatter, format_header, format_example, format_description
)
import argparse
from typing import Any


def setup_parser(subparsers: Any) -> None:
    """Set up the 'gc' command parser."""
    p_gc = subparsers.add_parser(
        "gc",
        help="Cleanup and optimize the local repository",
        description="""Run Garbage Collection (gc) to optimize the object database.

This command removes unreachable objects, compresses history, and performs general maintenance to keep the repository fast and lean.""",
        epilog="""

\033[1mEXAMPLES:\033[0m
  \033[1;34m⚓️ deep gc\033[0m
     Perform standard repository maintenance and optimization
  \033[1;34m⚓️ deep gc --prune=now\033[0m
     Immediately remove all unreachable objects
  \033[1;34m⚓️ deep gc --aggressive\033[0m
     Perform a deep, time-consuming compression of history
  \033[1;34m⚓️ deep gc --auto\033[0m
     Only run if the repository satisfies optimization thresholds
""",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    p_gc.add_argument("--auto", action="store_true", help="Only run if the repository needs optimization")
    p_gc.add_argument("--prune", action="store_true", help="Prune unreachable objects (older than 2 weeks by default)")
from deep.utils.ux import Color


def run(args) -> None:  # type: ignore[no-untyped-def]
    """Execute the ``gc`` command."""
    from deep.storage.transaction import TransactionManager
    from deep.core.constants import DEEP_DIR

    try:
        repo_root = find_repo()
        dg_dir = repo_root / DEEP_DIR
    except FileNotFoundError as exc:
        print(f"Deep: error: {exc}", file=sys.stderr)
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
        print(f"Found {unreachable_count} unreachable objects (out of {total_count} total).")
        print("Run without --dry-run to quarantine them.")
    else:
        if unreachable_count > 0:
            print(f"Relocated {unreachable_count} unreachable objects to quarantine.")
        else:
            print("No unreachable objects found.")
        print(f"Done. {total_count - unreachable_count} objects remaining in database.")
