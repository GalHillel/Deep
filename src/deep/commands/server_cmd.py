"""
deep.commands.server_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep server`` command implementation.
The Deep Platform Server - handles Deep protocol, REST API, and Web UI.
"""
from deep.core.config import Config
from deep.utils.ux import Color

from __future__ import annotations
from deep.core.errors import DeepCLIException

import asyncio
import time
from pathlib import Path
import sys

from deep.core.repository import find_repo, DEEP_DIR
from deep.network.daemon import DeepDaemon
from deep.web.dashboard import DashboardHandler

import argparse
from typing import Any

def setup_parser(subparsers: Any) -> None:
    """Set up the 'server' command parser."""
    p_server = subparsers.add_parser(
        "server",
        help="Start the Deep platform server instance",
        description="""Launch an integrated Deep platform server.

This command starts a multi-threaded service providing the Deep smart protocol, a RESTful API for integration, and the Deep Studio web interface for visual project management.""",
        epilog="""

\033[1mEXAMPLES:\033[0m
  \033[1;34m⚓️ deep server\033[0m
     Start the platform server on localhost:8080 (Web) and :8090 (Deep)
  \033[1;34m⚓️ deep server --host 0.0.0.0 --port 80\033[0m
     Run the server in production mode on port 80
  \033[1;34m⚓️ deep server --no-ui\033[0m
     Start the server without the web interface
""",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    p_server.add_argument("--host", default="127.0.0.1", help="The host address to bind to (default: 127.0.0.1)")
    p_server.add_argument("--port", type=int, default=8080, help="The base port for the platform server (default: 8080)")
from http.server import HTTPServer
import threading
import time

def run_web_server(repo_root: Path, host: str, port: int):
    from deep.core.constants import DEEP_DIR
    dg_dir = repo_root / DEEP_DIR
    DashboardHandler.dg_dir = dg_dir
    DashboardHandler.repo_root = repo_root
    
    httpd = HTTPServer((host, port), DashboardHandler)
    print(Color.wrap(Color.CYAN, f"Deep Studio UI running at http://{host}:{port}"))
    httpd.serve_forever()

def run_mirror_sync(repo_root: Path):
    dg_dir = repo_root / DEEP_DIR
    manager = MirrorManager(dg_dir)
    config = Config(repo_root)
    # Background sync needs a token if remote is authenticated
    # We'll use the local one if available
    while True:
        token = config.get("auth.token")
        try:
            manager.sync_all(auth_token=token)
        except Exception:
            pass # Silent in background
        time.sleep(300) # Sync every 5 minutes
    """Execute the ``server`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Deep: error: {exc}", file=sys.stderr)
        raise DeepCLIException(1)

    host = getattr(args, "host", "127.0.0.1")
    port = getattr(args, "port", 8080)
    git_port = port + 10 # Default deep daemon port is offset

    # Start the Web UI + REST API in a background thread
    web_thread = threading.Thread(target=run_web_server, args=(repo_root, host, port), daemon=True)
    web_thread.start()
    
    # Start background mirror sync
    mirror_thread = threading.Thread(target=run_mirror_sync, args=(repo_root,), daemon=True)
    mirror_thread.start()
    
    # Start the Deep protocol daemon in the main loop
    daemon = DeepDaemon(repo_root, host=host, port=git_port)
    
    print(Color.wrap(Color.GREEN, f"Deep Platform Server starting on host {host}..."))
    print(Color.wrap(Color.DIM, f"  Web/API: http://{host}:{port}"))
    print(Color.wrap(Color.DIM, f"  Deep:     deep://{host}:{git_port}"))
    
    try:
        asyncio.run(daemon.start())
    except KeyboardInterrupt:
        print("\nServer stopped by user.")
    except Exception as e:
        print(f"Fatal error in server: {e}", file=sys.stderr)
        raise DeepCLIException(1)
