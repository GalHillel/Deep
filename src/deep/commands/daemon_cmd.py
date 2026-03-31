"""
deep.commands.daemon_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep daemon`` command implementation.
"""

from __future__ import annotations
from deep.core.errors import DeepCLIException

import asyncio
import sys
from pathlib import Path

from deep.core.repository import find_repo
from deep.network.daemon import DeepDaemon
from deep.utils.ux import (
    DeepHelpFormatter, format_header, format_example, format_description
)
import argparse
from typing import Any


def setup_parser(subparsers: Any) -> None:
    """Set up the 'daemon' command parser."""
    p_daemon = subparsers.add_parser(
        "daemon",
        help="Start a background Deep service",
        description="""Run a background process to handle periodic maintenance, synchronization, and object serving.

The daemon allows other peers to discover and pull from your repository over the network.""",
        epilog="""

\033[1mEXAMPLES:\033[0m
\033[1m  LOCAL SERVICE:\033[0m
  \033[1;34m⚓️ deep daemon\033[0m
     Start the service on the default local port (8888)
  \033[1;34m⚓️ deep daemon --port 9000\033[0m
     Start the service on a custom port

\033[1m  NETWORK DISCOVERY:\033[0m
  \033[1;34m⚓️ deep daemon --host 0.0.0.0\033[0m
     Allow connections from any network interface
""",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    p_daemon.add_argument("--host", default="127.0.0.1", help="The host address to bind to (default: 127.0.0.1)")
    p_daemon.add_argument("--port", type=int, default=8888, help="The port number to listen on (default: 8888)")


def run(args) -> None:  # type: ignore[no-untyped-def]
    """Execute the ``daemon`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Deep: error: {exc}", file=sys.stderr)
        raise DeepCLIException(1)

    host = getattr(args, "host", "127.0.0.1")
    port = getattr(args, "port", 8888)

    daemon = DeepDaemon(repo_root, host=host, port=port)
    
    print(Color.wrap(Color.CYAN, f"Starting Deep Daemon on {host}:{port}..."))
    print(Color.wrap(Color.DIM, f"Serving repository: {repo_root}"))
    
    try:
        asyncio.run(daemon.start())
    except KeyboardInterrupt:
        print("\nDaemon stopped by user.")
    except Exception as e:
        print(f"Fatal error in daemon: {e}", file=sys.stderr)
        raise DeepCLIException(1)
