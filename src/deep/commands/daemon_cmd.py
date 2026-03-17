"""
deep.commands.daemon_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep daemon`` command implementation.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from deep.core.repository import find_repo
from deep.network.daemon import DeepGitDaemon
from deep.utils.ux import Color


def run(args) -> None:  # type: ignore[no-untyped-def]
    """Execute the ``daemon`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"DeepGit: error: {exc}", file=sys.stderr)
        sys.exit(1)

    host = getattr(args, "host", "127.0.0.1")
    port = getattr(args, "port", 8888)

    daemon = DeepGitDaemon(repo_root, host=host, port=port)
    
    print(Color.wrap(Color.CYAN, f"Starting DeepGit Daemon on {host}:{port}..."))
    print(Color.wrap(Color.DIM, f"Serving repository: {repo_root}"))
    
    try:
        asyncio.run(daemon.start())
    except KeyboardInterrupt:
        print("\nDaemon stopped by user.")
    except Exception as e:
        print(f"Fatal error in daemon: {e}", file=sys.stderr)
        sys.exit(1)
