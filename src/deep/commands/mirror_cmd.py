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
from deep.utils.ux import DeepHelpFormatter, format_example
import argparse
from typing import Any


from deep.utils.ux import (
    DeepHelpFormatter, format_header, format_example, format_description
)
import argparse
from typing import Any


def setup_parser(subparsers: Any) -> None:
    """Set up the 'mirror' command parser."""
    p_mirror = subparsers.add_parser(
        "mirror",
        help="Manage repository mirrors",
        description="""Mirror your repository to multiple remote locations simultaneously.

Mirrors are updated in parallel to ensure your project exists across redundant endpoints.""",
        epilog="""

\033[1mEXAMPLES:\033[0m
  \033[1;34m⚓️ deep mirror add https://backup-server.com/repo.deep\033[0m
     Add a new mirror destination
  \033[1;34m⚓️ deep mirror list\033[0m
     List all configured mirror endpoints
  \033[1;34m⚓️ deep mirror sync\033[0m
     Synchronize all mirrors with the current local state
  \033[1;34m⚓️ deep mirror remove 2\033[0m
     Remove a mirror by its index
""",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    ms = p_mirror.add_subparsers(dest="mirror_command", metavar="ACTION")
    ms.add_parser("add", help="Add a new mirror").add_argument("url", help="The URL to mirror to")
    ms.add_parser("sync", help="Synchronize all mirrors")
    ms.add_parser("list", help="List all configured mirrors")

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
        from deep.storage.transaction import TransactionManager
        with TransactionManager(dg_dir) as tm:
            tm.begin("mirror-sync")
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
            tm.commit()
                    
    elif cmd == "list":
        mirrors = manager.list_mirrors()
        if not mirrors:
            print("No mirrors configured.")
            return
        print("Configured mirrors:")
        for m in mirrors:
            print(f"  - {m}")
