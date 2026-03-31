"""
deep.commands.graph_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep graph`` command — visualises commit history.
"""

from __future__ import annotations
from deep.core.errors import DeepCLIException
import sys
from deep.core.repository import find_repo, DEEP_DIR
from deep.core.graph import get_history_graph, render_graph
from deep.utils.ux import DeepHelpFormatter, format_example
from typing import Any


def setup_parser(subparsers: Any) -> None:
    """Set up the 'graph' command parser."""
    p_graph = subparsers.add_parser(
        "graph",
        help="Visualize the commit graph",
        description="Renders a text-based ASCII visualization of the commit history graph.",
        epilog=f"""
Examples:
{format_example("deep graph", "Visualize history for current branch")}
{format_example("deep graph --all", "Include all branches and tags")}
""",
        formatter_class=DeepHelpFormatter,
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
