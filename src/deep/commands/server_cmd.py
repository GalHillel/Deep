"""
deep.commands.server_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep server`` command implementation.
The DeepGit Platform Server - handles Git protocol, REST API, and Web UI.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from deep.core.repository import find_repo, DEEP_GIT_DIR
from deep.network.daemon import DeepGitDaemon
from deep.web.dashboard import DashboardHandler
from deep.utils.ux import Color
from deep.core.mirror import MirrorManager
from deep.core.config import Config
from http.server import HTTPServer
import threading
import time

def run_web_server(repo_root: Path, host: str, port: int):
    from deep.core.repository import DEEP_GIT_DIR
    dg_dir = repo_root / DEEP_GIT_DIR
    DashboardHandler.dg_dir = dg_dir
    DashboardHandler.repo_root = repo_root
    
    httpd = HTTPServer((host, port), DashboardHandler)
    print(Color.wrap(Color.CYAN, f"DeepGit Web UI running at http://{host}:{port}"))
    httpd.serve_forever()

def run_mirror_sync(repo_root: Path):
    dg_dir = repo_root / DEEP_GIT_DIR
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
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    host = getattr(args, "host", "127.0.0.1")
    port = getattr(args, "port", 8080)
    git_port = port + 10 # Default git daemon port is offset

    # Start the Web UI + REST API in a background thread
    web_thread = threading.Thread(target=run_web_server, args=(repo_root, host, port), daemon=True)
    web_thread.start()
    
    # Start background mirror sync
    mirror_thread = threading.Thread(target=run_mirror_sync, args=(repo_root,), daemon=True)
    mirror_thread.start()
    
    # Start the Git protocol daemon in the main loop
    daemon = DeepGitDaemon(repo_root, host=host, port=git_port)
    
    print(Color.wrap(Color.GREEN, f"DeepGit Platform Server starting on host {host}..."))
    print(Color.wrap(Color.DIM, f"  Web/API: http://{host}:{port}"))
    print(Color.wrap(Color.DIM, f"  Git:     deep://{host}:{git_port}"))
    
    try:
        asyncio.run(daemon.start())
    except KeyboardInterrupt:
        print("\nServer stopped by user.")
    except Exception as e:
        print(f"Fatal error in server: {e}", file=sys.stderr)
        sys.exit(1)
