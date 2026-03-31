"""
deep.commands.studio_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep studio`` command — launches the Deep Studio dashboard.
"""

from __future__ import annotations
from deep.core.errors import DeepCLIException

import sys
from deep.core.repository import find_repo
from deep.utils.ux import (
    DeepHelpFormatter, format_header, format_example, format_description
)
from typing import Any


def setup_parser(subparsers: Any) -> None:
    """Set up the 'studio' command parser."""
    p_studio = subparsers.add_parser(
        "studio",
        help="Launch the Deep Studio web interface",
        description=format_description("Start the local Deep Studio dashboard. Studio provides a premium, futuristic web interface for visual repository inspection, branch graphing, AI-assisted code review, and issue management."),
        epilog=f"""
{format_header("Examples")}
{format_example("deep studio", "Launch the Studio dashboard on the default port (9000)")}
{format_example("deep studio --port 8080", "Launch Studio on a custom port")}
{format_example("deep studio --no-browser", "Start the Studio server without auto-opening a browser")}
""",
        formatter_class=DeepHelpFormatter,
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
