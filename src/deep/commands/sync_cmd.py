"""
deep.commands.sync_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Deep ``sync`` command implementation.
High-level orchestration for repository synchronization.
"""

from __future__ import annotations
from deep.core.errors import DeepCLIException

from deep.core.repository import find_repo
from deep.utils.ux import (
    DeepHelpFormatter, format_header, format_example, format_description
)
from typing import Any


def setup_parser(subparsers: Any) -> None:
    """Set up the 'sync' command parser."""
    p_sync = subparsers.add_parser(
        "sync",
        help="Synchronize with remotes, mirrors and peers",
        description="""Perform a high-level synchronization of your repository state.

This command orchestrates fetching changes from upstream sources and optionally pushing to configured mirrors, ensuring your project is fully up-to-date across all endpoints.""",
        epilog="""

\033[1mEXAMPLES:\033[0m
  \033[1;34m⚓️ deep sync\033[0m
     Synchronize with the default 'origin' remote
  \033[1;34m⚓️ deep sync origin\033[0m
     Explicitly sync with the 'origin' remote
  \033[1;34m⚓️ deep sync --all\033[0m
     Synchronize with all configured remotes and mirrors
  \033[1;34m⚓️ deep sync --peer <url>\033[0m
     Synchronize directly with a specific P2P peer
""",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    p_sync.add_argument("peer", nargs="?", help="The remote name, URL, or peer address to sync with (default: origin)")
    p_sync.add_argument("--all", action="store_true", help="Synchronize with all configured remotes and mirrors")
    p_sync.add_argument("--prune", action="store_true", help="Prune tracking branches that no longer exist on the remote")


def ns(**kwargs):
    import argparse
    return argparse.Namespace(**kwargs)


def run(args) -> None:  # type: ignore[no-untyped-def]
    """Execute the ``sync`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Deep: error: {exc}", file=sys.stderr)
        raise DeepCLIException(1)

    peer = getattr(args, "peer", None)
    
    # Sync is essentially a pull from the peer or origin
    url = peer or "origin"
    
    print(f"Deep: syncing with '{url}'...")
    
    # We call pull_cmd.run with the url
    # We need to know the current branch to pull into it
    from deep.core.refs import get_current_branch
    from deep.core.constants import DEEP_DIR
    branch = get_current_branch(repo_root / DEEP_DIR)
    
    if not branch:
        print("Deep: error: cannot sync in detached HEAD state", file=sys.stderr)
        raise DeepCLIException(1)
        
    try:
        pull_cmd.run(ns(url=url, branch=branch))
        print("Deep: sync complete.")
    except Exception as e:
        print(f"Deep: error: sync failed: {e}", file=sys.stderr)
        raise DeepCLIException(1)
