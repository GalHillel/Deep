"""
deep.commands.init_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Deep ``init`` command implementation.
"""

from __future__ import annotations
from deep.core.errors import DeepCLIException

import sys
from deep.core.repository import init_repo
from deep.utils.ux import (
    format_option
)
import argparse
from typing import Any
from pathlib import Path

def setup_parser(subparsers: Any) -> None:
    """Set up the 'init' command parser."""
    p_init = subparsers.add_parser(
        "init",
        help="Initialize a new empty Deep repository",
        description="""Create an empty Deep repository or reinitialize an existing one.

This sets up the internal .deep structures and configuration.""",
        epilog="""

\033[1mEXAMPLES:\033[0m
  \033[1;34m⚓️ deep init\033[0m
     Initialize in the current directory
  \033[1;34m⚓️ deep init my-project\033[0m
     Create 'my-project' directory and initialize there
  \033[1;34m⚓️ deep init --bare\033[0m
     Create a bare repository for server use
""",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    p_init.add_argument("path", nargs="?", default=None, help="The target directory for the repository (default: current directory)")
    p_init.add_argument("--bare", action="store_true", help="Create a bare repository (without a working tree)")

def run(args) -> None:  # type: ignore[no-untyped-def]
    """Execute the ``init`` command."""
    path = Path(args.path) if args.path else Path.cwd()
    bare = getattr(args, "bare", False)
    try:
        dg = init_repo(path, bare=bare)
        from deep.utils.logger import setup_repo_logging
        setup_repo_logging(path, is_bare=bare)
        print(f"Deep: initialized empty repository in {dg}")
    except FileExistsError as exc:
        print(f"Deep: error: {exc}", file=sys.stderr)
        raise DeepCLIException(1)
