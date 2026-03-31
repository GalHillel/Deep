"""
deep.commands.init_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Deep ``init`` command implementation.
"""

from __future__ import annotations
from deep.core.errors import DeepCLIException

import sys
from deep.core.repository import init_repo
from deep.utils.ux import DeepHelpFormatter, format_example
from typing import Any


def setup_parser(subparsers: Any) -> None:
    """Set up the 'init' command parser."""
    p_init = subparsers.add_parser(
        "init",
        help="Initialize a new empty Deep repository",
        description="Create an empty Deep repository or reinitialize an existing one.",
        epilog=f"""
Examples:
{format_example("deep init", "Initialize in the current directory")}
{format_example("deep init my-project", "Create 'my-project' and initialize there")}
""",
        formatter_class=DeepHelpFormatter,
    )
    p_init.add_argument("path", nargs="?", help="The target directory for the repository")
    p_init.add_argument("--bare", action="store_true", help="Create a bare repository")


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
