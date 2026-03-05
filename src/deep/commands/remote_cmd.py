"""
deep.commands.remote_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep remote`` command implementation.
"""

from __future__ import annotations

import sys
from pathlib import Path

from deep.core.config import Config
from deep.core.repository import find_repo
from deep.utils.ux import Color

def run(args) -> None:
    """Execute the ``remote`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

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
