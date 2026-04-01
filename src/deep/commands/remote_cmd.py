"""
deep.commands.remote_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep remote`` command implementation.
"""

from __future__ import annotations
from deep.core.errors import DeepCLIException

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
        print(f"Deep: error: {exc}", file=sys.stderr)
        raise DeepCLIException(1)

    config = Config(repo_root)

    if args.remote_command == "add":
        name = args.name
        url = args.url
        if not name or not url:
            print("Deep: error: both remote name and URL are required for 'add'", file=sys.stderr)
            raise DeepCLIException(1)
        
        # Check if remote already exists
        if config.parser.has_section(f"remote.{name}"):
            print(f"Deep: error: remote '{name}' already exists", file=sys.stderr)
            raise DeepCLIException(1)

        config.set_local(f"remote.{name}.url", url)
        print(f"Added remote '{name}' with URL '{url}'")

    elif args.remote_command == "remove":
        name = args.name
        if not name:
            print("Deep: error: remote name required for 'remove'", file=sys.stderr)
            raise DeepCLIException(1)
        
        if not config.parser.has_section(f"remote.{name}"):
            print(f"Deep: error: remote '{name}' not found", file=sys.stderr)
            raise DeepCLIException(1)

        config.remove_local(f"remote.{name}")
        print(f"Removed remote '{name}'")

    else:
        # Listing remotes
        remotes = {}
        for section in config.parser.sections():
            if section.startswith("remote."):
                name = section[7:] # strip "remote."
                url = config.parser.get(section, "url", fallback="unknown")
                remotes[name] = url
        
        if not remotes:
            return
            
        for name in sorted(remotes.keys()):
            url = remotes[name]
            print(f"{Color.wrap(Color.BOLD, name)}\t{url}")
