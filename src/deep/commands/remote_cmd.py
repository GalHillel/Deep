"""
deep.commands.remote_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep remote`` command implementation.
"""
from deep.utils.ux import Color
from typing import List

from __future__ import annotations
from deep.core.errors import DeepCLIException

import sys
from pathlib import Path

from deep.core.config import Config
from deep.core.repository import find_repo

import argparse
from typing import Any

def setup_parser(subparsers: Any) -> None:
    """Set up the 'remote' command parser."""
    p_remote = subparsers.add_parser(
        "remote",
        help="Manage set of tracked repositories",
        description="""Manage the set of repositories ('remotes') whose branches you track.

Remotes are identified by a name (like 'origin') and a URL/path.""",
        epilog="""

\033[1mEXAMPLES:\033[0m
  \033[1;34m⚓️ deep remote\033[0m
     List all configured remotes and their URLs
  \033[1;34m⚓️ deep remote add origin <url>\033[0m
     Add a new remote named 'origin'
  \033[1;34m⚓️ deep remote remove dev\033[0m
     Remove the 'dev' remote from configuration
  \033[1;34m⚓️ deep remote set-url origin <new-url>\033[0m
     Update the URL for 'origin'
""",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    rs = p_remote.add_subparsers(dest="remote_command", metavar="ACTION")
    
    p_add = rs.add_parser("add", help="Add a new remote")
    p_add.add_argument("name", help="The name for the new remote")
    p_add.add_argument("url", help="The URL or path for the new remote")
    
    p_rm = rs.add_parser("remove", help="Remove an existing remote")
    p_rm.add_argument("name", help="The name of the remote to remove")

def run(args) -> None:
    """Execute the ``remote`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise DeepCLIException(1)

    config = Config(repo_root)

    if args.remote_command == "add":
        name = args.name
        url = args.url
        config.set_local(f"remote.{name}.url", url)
        print(f"Added remote '{name}' with URL '{url}'")
    elif args.remote_command == "remove":
        name = args.name
        config.remove_local(f"remote.{name}")
        print(f"Removed remote '{name}'")
    else:
        # Listing remotes (default)
        remotes = []
        for section in config.parser.sections():
            if section.startswith("remote."):
                parts = section.split(".")
                if len(parts) >= 2:
                    remotes.append(parts[1])
        
        # Deduplicate and sort
        remotes = sorted(list(set(remotes)))
        if not remotes:
            return
            
        for r in remotes:
            url = config.parser.get(f"remote.{r}", "url", fallback="unknown")
            print(f"{Color.wrap(Color.BOLD, r)}\t{url}")
