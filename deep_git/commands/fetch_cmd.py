"""
deep_git.commands.fetch_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deepgit fetch`` command implementation.
"""

from __future__ import annotations

import sys
from pathlib import Path

from deep_git.core.repository import find_repo, DEEP_GIT_DIR
from deep_git.core.refs import update_branch
from deep_git.network.client import RemoteClient


def run(args) -> None:  # type: ignore[no-untyped-def]
    """Execute the ``fetch`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    url = args.url
    if ":" not in url:
        print("Error: URL must be in host:port format", file=sys.stderr)
        sys.exit(1)
        
    host, port_str = url.split(":", 1)
    port = int(port_str)
    
    sha = args.sha
    client = RemoteClient(host, port)
    try:
        client.connect()
        print(f"Fetching {sha} from {url}...")
        count = client.fetch(repo_root / DEEP_GIT_DIR / "objects", sha)
        print(f"Fetched {count} objects.")
        
        # update_branch(repo_root / DEEP_GIT_DIR, "FETCH_HEAD", sha)
    except Exception as e:
        print(f"Fetch failed: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        client.disconnect()
