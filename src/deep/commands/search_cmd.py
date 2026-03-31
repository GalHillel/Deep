"""
deep.commands.search_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep search`` command implementation.
"""

from __future__ import annotations
from deep.core.errors import DeepCLIException

import sys
from pathlib import Path

from deep.core.constants import DEEP_DIR
from deep.core.repository import find_repo
from deep.core.search import search_history
from deep.utils.ux import (
    DeepHelpFormatter, format_header, format_example, format_description
)
from typing import Any


def setup_parser(subparsers: Any) -> None:
    """Set up the 'search' command parser."""
    p_search = subparsers.add_parser(
        "search",
        help="Search history and object database for patterns",
        description=format_description("Deep Search provides a high-performance engine for finding strings and regular expressions across your entire repository history. It scans commit messages, file contents, and object metadata to help you locate changes and identify patterns."),
        epilog=f"""
{format_header("Examples")}
{format_example("deep search 'TODO'", "Search repository history and current state for 'TODO'")}
{format_example("deep search --regex 'FIXME.*[0-9]+'", "Perform a regular expression search across all objects")}
{format_example("deep search 'main' --path src/", "Limit search to the 'src/' directory")}
""",
        formatter_class=DeepHelpFormatter,
    )
    p_search.add_argument("query", help="The string or pattern to search for")
    p_search.add_argument("--regex", action="store_true", help="Interpret query as a regular expression")


def run(args) -> None:
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Deep: error: {exc}", file=sys.stderr)
        raise DeepCLIException(1)

    dg_dir = repo_root / DEEP_DIR
    pattern = getattr(args, "query", None) or getattr(args, "pattern", None)
    
    print(f"Searching history for '{pattern}'...")
    results = search_history(dg_dir, pattern)
    
    if not results:
        print("No matches found.")
        return
        
    for res in results:
        print(f"{res.commit_sha[:7]}:{res.rel_path}:{res.line_num}: {res.content}")
    
    print(f"\nFound {len(results)} match(es).")
    sys.exit(0)
