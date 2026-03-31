"""
deep.commands.graph_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep graph`` command — visualises commit history.
"""
from deep.core.constants import DEEP_DIR

from __future__ import annotations
from deep.core.errors import DeepCLIException
import sys
from deep.core.repository import find_repo, DEEP_DIR
from deep.core.graph import get_history_graph, render_graph

import argparse
from typing import Any

def setup_parser(subparsers: Any) -> None:
    """Set up the 'graph' command parser."""
    p_graph = subparsers.add_parser(
        "graph",
        help="Visualize the commit graph",
        description="""Render a high-fidelity, text-based ASCII visualization of the repository's commit history.

The graph displays the relationship between commits, branches, and tags, making it easy to track merges, forks, and the overall evolution of the project.""",
        epilog="""

\033[1mEXAMPLES:\033[0m
  \033[1;34m⚓️ deep graph\033[0m
     Visualize the history of the current branch
  \033[1;34m⚓️ deep graph --all\033[0m
     Include all references (branches, tags, remotes) in the graph
  \033[1;34m⚓️ deep graph -n 20\033[0m
     Limit the graph to the 20 most recent commits
  \033[1;34m⚓️ deep graph --oneline\033[0m
     Display a condensed, single-line-per-commit graph
""",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    p_graph.add_argument("--all", action="store_true", help="Include all references (branches and tags) in the graph")
    p_graph.add_argument("-n", "--max-count", type=int, default=100, help="Maximum number of commits to display (default: 100)")

def run(args) -> None:  # type: ignore[no-untyped-def]
    """Execute the ``graph`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Deep: error: {exc}", file=sys.stderr)
        raise DeepCLIException(1)

    dg_dir = repo_root / DEEP_DIR
    
    nodes = get_history_graph(
        dg_dir, 
        max_count=args.max_count, 
        all_refs=args.all
    )
    
    if not nodes:
        print("No commits found.")
        return

    render_graph(nodes)
