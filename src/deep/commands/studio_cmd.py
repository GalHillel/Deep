"""
deep.commands.studio_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep studio`` command — launches the Deep Studio dashboard.
"""

from __future__ import annotations
from deep.core.errors import DeepCLIException

import sys
from pathlib import Path

from deep.core.repository import find_repo


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
