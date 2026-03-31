"""
deep.commands.sync_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Deep ``sync`` command implementation.
High-level orchestration for repository synchronization.
"""

from __future__ import annotations
from deep.core.errors import DeepCLIException

import sys
from pathlib import Path

from deep.commands import pull_cmd
from deep.core.repository import find_repo


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
