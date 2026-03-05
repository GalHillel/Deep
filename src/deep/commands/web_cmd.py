"""
deep.commands.web_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep web`` command — launches the Web Dashboard.
"""

from __future__ import annotations

import sys
from pathlib import Path

from deep.core.repository import find_repo


def run(args) -> None:
    """Execute the ``web`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    from deep.web.dashboard import start_dashboard

    port = args.port if hasattr(args, "port") else 9000
    start_dashboard(repo_root, port=port)
