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
from deep.utils.ux import DeepHelpFormatter, format_example
from typing import Any


def setup_parser(subparsers: Any) -> None:
    """Set up the 'remote' command parser."""
    p_remote = subparsers.add_parser(
        "remote",
        help="Manage set of tracked repositories",
        description="Manage the set of repositories ('remotes') whose branches you track.",
        epilog=f"""
Examples:
{format_example("deep remote", "List all configured remotes")}
{format_example("deep remote add origin <url>", "Add a new remote named 'origin'")}
{format_example("deep remote remove origin", "Remove 'origin' from configuration")}
""",
        formatter_class=DeepHelpFormatter,
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
