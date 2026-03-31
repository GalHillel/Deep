"""
deep.commands.studio_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep studio`` command — launches the Deep Studio dashboard.
"""

from __future__ import annotations
from deep.core.errors import DeepCLIException

import sys
from deep.core.repository import find_repo

import argparse
from typing import Any

def setup_parser(subparsers: Any) -> None:
    """Set up the 'studio' command parser."""
    p_studio = subparsers.add_parser(
        "studio",
        help="Launch the Deep Studio web interface",
        description="""Start the local Deep Studio dashboard.

Studio provides a premium, futuristic web interface for visual repository inspection, branch graphing, AI-assisted code review, and issue management.""",
        epilog="""

\033[1mEXAMPLES:\033[0m
  \033[1;34m⚓️ deep studio\033[0m
     Launch the Studio dashboard on the default port (9000)
  \033[1;34m⚓️ deep studio --port 8080\033[0m
     Launch Studio on a custom port
  \033[1;34m⚓️ deep studio --no-browser\033[0m
     Start the Studio server without auto-opening a browser
""",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    p_studio.add_argument("--port", type=int, default=9000, help="The port number to host the Studio dashboard (default: 9000)")

def run(args) -> None:
    """Execute the ``studio`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Deep: error: {exc}", file=sys.stderr)
        raise DeepCLIException(1)

    from deep.web.dashboard import start_dashboard

    port = args.port if hasattr(args, "port") else 9000
    start_dashboard(repo_root, port=port)
