"""
deep.commands.init_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~
DeepGit ``init`` command implementation.
"""

from __future__ import annotations

import sys
from pathlib import Path

from deep.core.repository import init_repo


def run(args) -> None:  # type: ignore[no-untyped-def]
    """Execute the ``init`` command."""
    path = Path(args.path) if args.path else Path.cwd()
    try:
        dg = init_repo(path)
        print(f"DeepGit: initialized empty repository in {dg}")
    except FileExistsError as exc:
        print(f"DeepGit: error: {exc}", file=sys.stderr)
        sys.exit(1)
