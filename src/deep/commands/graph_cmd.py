"""
deep.commands.graph_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep graph`` command — visualises commit history.
"""

from __future__ import annotations
import sys
from deep.core.repository import find_repo, DEEP_DIR
from deep.core.graph import get_history_graph, render_graph

def run(args) -> None:  # type: ignore[no-untyped-def]
    """Execute the ``graph`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Deep: error: {exc}", file=sys.stderr)
        sys.exit(1)

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
