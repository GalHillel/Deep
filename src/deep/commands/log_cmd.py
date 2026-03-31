"""
deep.commands.log_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~
Deep ``log`` command implementation.
"""

from __future__ import annotations
from deep.core.errors import DeepCLIException

import sys
from pathlib import Path

from deep.storage.objects import Commit, read_object
from deep.core.refs import get_commit_decorations, log_history, resolve_head
from deep.core.constants import DEEP_DIR
from deep.core.repository import find_repo
from deep.utils.ux import DeepHelpFormatter, format_example
import argparse
from typing import Any


from deep.utils.ux import (
    DeepHelpFormatter, format_header, format_example, format_description
)
import argparse
from typing import Any


def setup_parser(subparsers: Any) -> None:
    """Set up the 'log' command parser."""
    p_log = subparsers.add_parser(
        "log",
        help="Display commit history logs",
        description="""Browse through the commit history of the current branch or a specified commit range.

Displays commit SHAs, authors, dates, and messages with support for visualizations and concise formatting.""",
        epilog="""

\033[1mEXAMPLES:\033[0m
  \033[1;34m⚓️ deep log\033[0m
     Show full detailed logs with authors and dates
  \033[1;34m⚓️ deep log --oneline\033[0m
     Show a concise summary (one line per commit)
  \033[1;34m⚓️ deep log -n 10\033[0m
     Limit the output to the last 10 commits
  \033[1;34m⚓️ deep log --graph\033[0m
     Visualize history with an ASCII-based commit graph
  \033[1;34m⚓️ deep log --oneline --graph\033[0m
     Visualize history in a compact graph format
""",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    p_log.add_argument("--oneline", action="store_true", help="Display each commit entry on a single concise line")
    p_log.add_argument("-n", "--max-count", type=int, help="Limit the number of commits to display")
    p_log.add_argument("--graph", action="store_true", help="Visualize history with an ASCII-based commit graph")
    p_log.add_argument("--all", action="store_true", help="Show history for all branches and refs")
from deep.utils.ux import Color
from deep.utils.utils import format_date


def run(args) -> None:  # type: ignore[no-untyped-def]
    """Execute the ``log`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Deep: error: {exc}", file=sys.stderr)
        raise DeepCLIException(1)

    dg_dir = repo_root / DEEP_DIR
    objects_dir = dg_dir / "objects"

    if getattr(args, "graph", False):
        from deep.core.graph import get_history_graph, render_graph
        max_count = getattr(args, "max_count", 100)
        nodes = get_history_graph(dg_dir, max_count=max_count)
        if not nodes:
            print("No commits yet.")
        else:
            render_graph(nodes)
        return

    shas = log_history(dg_dir)
    if not shas:
        print("No commits yet.")
        return

    if hasattr(args, "max_count") and args.max_count is not None:
        shas = shas[:args.max_count]

    decs = get_commit_decorations(dg_dir)

    for sha in shas:
        obj = read_object(objects_dir, sha)
        if not isinstance(obj, Commit):
            continue
        
        dec_str = ""
        if sha in decs:
            colored_decs = []
            for dec in decs[sha]:
                if "HEAD" in dec:
                    colored_decs.append(Color.wrap(Color.CYAN, dec))
                elif "tag: " in dec:
                    colored_decs.append(Color.wrap(Color.YELLOW, dec))
                else:
                    colored_decs.append(Color.wrap(Color.GREEN, dec))
            
            paren_start = Color.wrap(Color.YELLOW, "(")
            paren_end = Color.wrap(Color.YELLOW, ")")
            dec_str = f" {paren_start}{', '.join(colored_decs)}{paren_end}"
            
        is_graph = getattr(args, "graph", False)
        is_oneline = getattr(args, "oneline", False)
        graph_prefix = "* " if is_graph else ""

        if is_oneline:
            title = obj.message.splitlines()[0] if obj.message else ""
            short_sha = Color.wrap(Color.YELLOW, sha[:7])
            print(f"{graph_prefix}{short_sha}{dec_str} {title}")
        else:
            print(f"{graph_prefix}{Color.wrap(Color.YELLOW, 'commit ' + sha)}{dec_str}")
            graph_pad = "| " if is_graph else ""
            print(f"{graph_pad}{Color.wrap(Color.BOLD, 'Author:')} {obj.author}")
            date_str = format_date(obj.timestamp, obj.timezone)
            print(f"{graph_pad}{Color.wrap(Color.BOLD, 'Date:')}   {date_str}")
            print(graph_pad.rstrip())
            for line in obj.message.splitlines():
                print(f"{graph_pad}    {line}")
            print(graph_pad.rstrip())
