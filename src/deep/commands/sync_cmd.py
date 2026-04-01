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


from deep.core.config import Config
from deep.core.constants import DEEP_DIR
from deep.core.refs import get_current_branch

def ns(**kwargs):
    import argparse
    # Ensure all pull_cmd expected args are present
    defaults = {"rebase": False, "url": None, "branch": None}
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)

def run(args) -> None:
    """Execute the ``sync`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Deep: error: {exc}", file=sys.stderr)
        raise DeepCLIException(1)

    dg_dir = repo_root / DEEP_DIR
    config = Config(repo_root)
    
    branch = get_current_branch(dg_dir)
    if not branch:
        print("Deep: error: cannot sync in detached HEAD state", file=sys.stderr)
        raise DeepCLIException(1)

    # 1. Determine the remote to sync with
    peer = getattr(args, "peer", None)
    if peer:
        url_or_name = peer
    else:
        # Check track configuration for the current branch
        url_or_name = config.get(f"branch.{branch}.remote") or "origin"

    print(f"Deep: syncing branch '{branch}' with '{url_or_name}'...")
    
    try:
        # Pull performs fetch + merge/rebase
        pull_cmd.run(ns(url=url_or_name, branch=branch))
        print("Deep: sync complete.")
    except Exception as e:
        if not isinstance(e, DeepCLIException):
            print(f"Deep: error: sync failed: {e}", file=sys.stderr)
        raise e
