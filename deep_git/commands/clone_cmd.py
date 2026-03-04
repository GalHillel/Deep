"""
deep_git.commands.clone_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deepgit clone`` command implementation.
"""

from __future__ import annotations

import sys
from pathlib import Path

from deep_git.core.repository import DEEP_GIT_DIR
from deep_git.core.refs import update_head, update_branch, resolve_head
from deep_git.network.client import RemoteClient
from deep_git.main import main


def run(args) -> None:  # type: ignore[no-untyped-def]
    """Execute the ``clone`` command."""
    url = args.url
    if ":" not in url:
        print("Error: URL must be in host:port format", file=sys.stderr)
        sys.exit(1)
        
    host, port_str = url.split(":", 1)
    port = int(port_str)
    
    target_dir = Path(args.dir or host)
    if target_dir.exists() and any(target_dir.iterdir()):
        print(f"Error: Target directory '{target_dir}' already exists and is not empty", file=sys.stderr)
        sys.exit(1)
        
    target_dir.mkdir(parents=True, exist_ok=True)
    
    # Init new repo
    import os
    old_cwd = os.getcwd()
    os.chdir(target_dir)
    try:
        main(["init"])
        
        # Connect to remote
        client = RemoteClient(host, port)
        client.connect()
        
        # Fetch initial state
        # For simplicity, we fetch 'main' branch
        # In real Git, we'd negotiate HEAD
        print(f"Cloning into '{target_dir}'...")
        
        # We need a SHA to fetch. Let's assume the remote has a 'main' branch.
        # In a real protocol, the handshake would include the remote HEAD.
        # For now, we'll try to fetch 'main'.
        # Actually, let's just fetch 'main' by name if we can, or expect a SHA.
        # Our daemon.py fetch currently takes a SHA.
        
        # We'll need a way to list-refs first.
        # Let's add a quick 'list-refs' command to the daemon later.
        # For now, let me assume the user provides a branch or we fetch 'main' SHA.
        
        # Let's try to fetch a default branch 'main'
        # We need to know its SHA. 
        # For this phase, let's assume the daemon sends its HEAD during handshake.
        # I'll update daemon.py to send HEAD in the capabilities pkt.
        
        # For now, let's just fetch the remote's main if we can.
        # I'll skip the automated fetch until I update the daemon.
        print("Connected to remote. Initialized empty repository.")
        
    finally:
        os.chdir(old_cwd)
