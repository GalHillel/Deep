"""
deep.commands.fetch_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep fetch`` command implementation.
"""

from __future__ import annotations

import sys
from pathlib import Path

from deep.core.repository import find_repo, DEEP_GIT_DIR
from deep.core.refs import update_branch, update_head
from deep.core.config import Config
from deep.network.client import get_remote_client


def run(args) -> None:  # type: ignore[no-untyped-def]
    """Execute the ``fetch`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    url_or_name = args.url
    config = Config(repo_root)
    url = config.get(f"remote.{url_or_name}.url", url_or_name)
    
    sha = args.sha
    from deep.storage.objects import read_object
    try:
        read_object(repo_root / DEEP_GIT_DIR / "objects", sha)
        print("Already up to date")
        return
    except FileNotFoundError:
        pass

    auth_token = config.get("auth.token")
    client = get_remote_client(url, auth_token=auth_token)
    try:
        client.connect()
        from deep.utils.ux import Color
        print(Color.wrap(Color.CYAN, f"Fetching {sha} from {url}..."))
        count = client.fetch(repo_root / DEEP_GIT_DIR / "objects", sha)
        print(f"Fetched {count} objects.")
        
        # update_branch(repo_root / DEEP_GIT_DIR, "FETCH_HEAD", sha)
    except Exception as e:
        print(f"Fetch failed: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        client.disconnect()
