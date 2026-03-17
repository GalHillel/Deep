"""
deep.commands.pull_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep pull <remote> <branch>`` command implementation.
"""

from __future__ import annotations

import sys
from argparse import Namespace
from pathlib import Path

from deep.core.repository import find_repo, DEEP_DIR
from deep.core.refs import update_branch, resolve_head, get_branch
from deep.core.config import Config
from deep.network.client import get_remote_client
from deep.utils.ux import Color

def run(args) -> None:
    """Execute the ``pull`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"DeepGit: error: {exc}", file=sys.stderr)
        sys.exit(1)

    url_or_name = args.url
    config = Config(repo_root)
    url = config.get(f"remote.{url_or_name}.url", url_or_name)
    
    branch = args.branch
    dg_dir = repo_root / DEEP_DIR

    auth_token = config.get("auth.token")
    client = get_remote_client(url, auth_token=auth_token)
    try:
        client.connect()
        print(Color.wrap(Color.CYAN, f"Pulling from {url}..."))
        
        # 1. Fetch
        # Discovery to find the SHA of the branch on remote
        refs = client.ls_refs()
        remote_ref = f"refs/heads/{branch}"
        remote_sha = refs.get(remote_ref)
        if not remote_sha:
            print(f"DeepGit: error: Remote branch '{branch}' not found", file=sys.stderr)
            sys.exit(1)
            
        print(f"Fetching {branch} ({remote_sha[:7]})...")
        client.fetch(dg_dir / "objects", remote_sha)
        
        # 2. Merge
        print(f"Merging {remote_sha[:7]} into current branch...")
        from deep.commands.merge_cmd import run as merge_run
        merge_args = Namespace(branch=remote_sha)
        merge_run(merge_args)
        
    except Exception as e:
        print(f"DeepGit: error: pull failed: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        client.disconnect()
