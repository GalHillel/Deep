"""
deep.commands.mirror_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep mirror`` command implementation.
"""

from __future__ import annotations
from deep.core.errors import DeepCLIException

import sys
from pathlib import Path

from deep.core.repository import find_repo, DEEP_DIR
from deep.core.mirror import MirrorManager
from deep.core.config import Config
from deep.utils.ux import Color

def run(args) -> None:
    """Execute the ``mirror`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Deep: error: {exc}", file=sys.stderr)
        raise DeepCLIException(1)

    dg_dir = repo_root / DEEP_DIR
    manager = MirrorManager(dg_dir)
    config = Config(repo_root)
    auth_token = config.get("auth.token")
    
    cmd = args.mirror_command
    
    if cmd == "add":
        manager.add_mirror(args.url)
        print(Color.wrap(Color.GREEN, f"Mirror added: {args.url}"))
        
    elif cmd == "sync":
        print(Color.wrap(Color.CYAN, "Synchronizing all mirrors..."))
        results = manager.sync_all(auth_token=auth_token)
        for url, res in results.items():
            print(f"\nMirror: {url}")
            if "error" in res:
                print(Color.wrap(Color.RED, f"  Error: {res['error']}"))
            elif not res:
                print(Color.wrap(Color.DIM, "  Everything up to date."))
            else:
                for k, v in res.items():
                    print(f"  {k}: {v}")
                    
    elif cmd == "list":
        mirrors = manager.list_mirrors()
        if not mirrors:
            print("No mirrors configured.")
            return
        print("Configured mirrors:")
        for m in mirrors:
            print(f"  - {m}")
