"""
deep.commands.init_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Deep ``init`` command implementation.
"""

from __future__ import annotations
from deep.core.errors import DeepCLIException

import sys
from pathlib import Path

from deep.core.repository import init_repo


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
