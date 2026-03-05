"""
deep.commands.pull_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep pull <remote> <branch>`` command implementation.
"""

from __future__ import annotations

import sys
from pathlib import Path

from deep.core.repository import find_repo, DEEP_GIT_DIR
from deep.core.refs import update_branch, resolve_head, get_branch
from deep.core.config import Config
from deep.network.client import get_remote_client
from deep.cli.main import main
from deep.utils.ux import Color

def run(args) -> None:
    """Execute the ``pull`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    url_or_name = args.url
    config = Config(repo_root)
    url = config.get(f"remote.{url_or_name}.url", url_or_name)
    
    branch = args.branch
    dg_dir = repo_root / DEEP_GIT_DIR

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
            print(f"Error: Remote branch '{branch}' not found", file=sys.stderr)
            sys.exit(1)
            
        print(f"Fetching {branch} ({remote_sha[:7]})...")
        client.fetch(dg_dir / "objects", remote_sha)
        
        # 2. Merge
        print(f"Merging {remote_sha[:7]} into current branch...")
        # We pass the SHA directly to the merge command.
        # We'll need to update merge_cmd.py to handle SHAs.
        main(["merge", remote_sha])
        
    except Exception as e:
        print(f"Pull failed: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        client.disconnect()
