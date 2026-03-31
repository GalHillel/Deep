"""
deep.commands.studio_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep studio`` command — launches the Deep Studio dashboard.
"""

from __future__ import annotations
from deep.core.errors import DeepCLIException

import sys
from deep.core.repository import find_repo
from deep.utils.ux import DeepHelpFormatter, format_example
from typing import Any


def setup_parser(subparsers: Any) -> None:
    """Set up the 'studio' command parser."""
    p_studio = subparsers.add_parser(
        "studio",
        help="Launch the Deep Studio web interface",
        description="Starts the local Deep Studio dashboard for visual inspection of the repository.",
        epilog=f"""
Examples:
{format_example("deep studio", "Launch Studio on default port 9000")}
{format_example("deep studio --port 8000", "Launch Studio on custom port")}
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
