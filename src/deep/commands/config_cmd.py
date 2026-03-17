"""
deep.commands.config_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep config [--global] <key> [<value>]`` command implementation.
"""

from __future__ import annotations

import sys

from deep.core.config import Config
from deep.core.repository import find_repo


def run(args) -> None:  # type: ignore[no-untyped-def]
    """Execute the ``config`` command."""
    is_global = getattr(args, "global_", False)
    
    try:
        repo_root = find_repo()
        config = Config(repo_root if not is_global else None)
    except FileNotFoundError:
        if not is_global:
            print("Deep: error: not in a Deep repository and --global not specified.", file=sys.stderr)
            sys.exit(1)
        config = Config(None)

    key = args.key
    value = getattr(args, "value", None)

    if value is not None:
        if is_global:
            config.set_global(key, value)
        else:
            config.set_local(key, value)
    else:
        val = config.get(key)
        if val is None:
            sys.exit(1)
        print(val)
