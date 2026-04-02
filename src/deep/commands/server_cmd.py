"""
deep.commands.server_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep server`` command implementation.
The Deep Platform Server - handles Deep protocol, REST API, and Web UI.
"""

from __future__ import annotations
from deep.core.errors import DeepCLIException

import asyncio
import time
from pathlib import Path
import sys
import os
import signal
import subprocess

from deep.core.repository import find_repo, DEEP_DIR
from deep.network.daemon import DeepDaemon
from deep.web.dashboard import DashboardHandler
from deep.utils.ux import Color, print_error, print_success, print_info
from deep.core.mirror import MirrorManager
from deep.core.config import Config
from http.server import HTTPServer
import threading

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
    while True:
        token = config.get("auth.token")
        try:
            manager.sync_all(auth_token=token)
        except Exception:
            pass # Silent in background
        time.sleep(300) # Sync every 5 minutes

def run(args) -> None:
    """Execute the ``server`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print_error(f"{exc}")
        raise DeepCLIException(1)

    cmd = getattr(args, "server_command", "status")
    pid_file = repo_root / DEEP_DIR / "server.pid"

    if cmd == "start":
        _start_server(repo_root, pid_file)
    elif cmd == "stop":
        _stop_server(pid_file)
    elif cmd == "status":
        _server_status(pid_file)
    elif cmd == "restart":
        _stop_server(pid_file)
        time.sleep(1)
        _start_server(repo_root, pid_file)
    elif cmd == "_serve":
        _internal_serve(repo_root, args)

def _start_server(repo_root: Path, pid_file: Path):
    """Launch the server in the background."""
    if _is_running(pid_file):
        print_error("Server is already running.")
        return

    print_info("Starting Deep Platform Server in background...")
    
    # Spawn background process
    # We use 'deep server _serve' to run the actual loops
    process = subprocess.Popen(
        [sys.executable, "-m", "deep.cli.main", "server", "_serve"],
        cwd=repo_root,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
        start_new_session=True if os.name != "nt" else False
    )
    
    pid_file.write_text(str(process.pid))
    print_success(f"Server started (PID: {process.pid})")

def _stop_server(pid_file: Path):
    """Stop the background server."""
    if not pid_file.exists():
        print_error("Server is not running (no PID file).")
        return

    try:
        pid = int(pid_file.read_text())
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True)
        else:
            os.kill(pid, signal.SIGTERM)
        
        pid_file.unlink()
        print_success("Server stopped.")
    except (ValueError, ProcessLookupError, PermissionError):
        print_error("Failed to stop server (PID might be stale). Cleaning up PID file.")
        if pid_file.exists():
            pid_file.unlink()

def _server_status(pid_file: Path):
    """Check if the server is running."""
    if _is_running(pid_file):
        pid = pid_file.read_text()
        print_success(f"Deep Platform Server is running (PID: {pid}).")
    else:
        print_info("Deep Platform Server is NOT running.")

def _is_running(pid_file: Path) -> bool:
    if not pid_file.exists():
        return False
    try:
        pid = int(pid_file.read_text())
        if os.name == "nt":
            # tasklist check for PID
            res = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, text=True)
            return str(pid) in res.stdout
        else:
            os.kill(pid, 0)
            return True
    except (ValueError, ProcessLookupError, Exception):
        return False

def _internal_serve(repo_root: Path, args):
    """The actual persistent worker loop."""
    host = "127.0.0.1"
    port = 8080
    git_port = 9091 # Default deep daemon port

    # Start threads
    threading.Thread(target=run_web_server, args=(repo_root, host, port), daemon=True).start()
    threading.Thread(target=run_mirror_sync, args=(repo_root,), daemon=True).start()
    
    # Start the Deep protocol daemon in the main loop
    daemon = DeepDaemon(repo_root, host=host, port=git_port)
    
    try:
        asyncio.run(daemon.start())
    except Exception:
        sys.exit(1)
