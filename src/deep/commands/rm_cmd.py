"""
deep.commands.rm_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep rm <file>`` command implementation.

Removes a file from both the working directory and the index.
"""

from __future__ import annotations
from deep.core.errors import DeepCLIException

import sys
from pathlib import Path

from deep.storage.index import remove_multiple_from_index
from deep.core.constants import DEEP_DIR
from deep.core.repository import find_repo
from deep.utils.ux import DeepHelpFormatter, format_example
from typing import Any


def setup_parser(subparsers: Any) -> None:
    """Set up the 'rm' command parser."""
    p_rm = subparsers.add_parser(
        "rm",
        help="Remove files from worktree and index",
        description="Remove files from the working directory and staging index.",
        epilog=f"""
Examples:
{format_example("deep rm file.txt", "Delete file and remove from index")}
{format_example("deep rm --cached file", "Keep file but remove from index")}
""",
        formatter_class=DeepHelpFormatter,
    )
    p_rm.add_argument("files", nargs="+", help="One or more files or directory paths to remove")
    p_rm.add_argument("--cached", action="store_true", help="Remove from the index only")
from deep.storage.transaction import TransactionManager


def run(args) -> None:  # type: ignore[no-untyped-def]
    """Execute the ``rm`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Deep: error: {exc}", file=sys.stderr)
        raise DeepCLIException(1)

    dg_dir = repo_root / DEEP_DIR

    with TransactionManager(dg_dir) as tm:
        tm.begin("rm")
        for file_path_str in args.files:
            file_path = Path(file_path_str).resolve()
            rel_path = file_path.relative_to(repo_root).as_posix()

            # Remove from index.
            from deep.storage.index import read_index_no_lock
            idx = read_index_no_lock(dg_dir)
            if rel_path not in idx.entries:
                print(f"Deep: error: '{rel_path}' is not tracked.", file=sys.stderr)
                raise DeepCLIException(1)
                
            remove_multiple_from_index(dg_dir, [rel_path])

            # Remove from working directory.
            if file_path.exists():
                file_path.unlink()

            print(f"rm '{rel_path}'")
        tm.commit()
