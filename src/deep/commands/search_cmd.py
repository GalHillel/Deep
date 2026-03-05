"""
deep.commands.search_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep search`` command implementation.
"""

from __future__ import annotations

import sys
from pathlib import Path

from deep.core.repository import DEEP_GIT_DIR, find_repo
from deep.core.search import search_history


def run(args) -> None:
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    dg_dir = repo_root / DEEP_GIT_DIR
    pattern = getattr(args, "query", None) or getattr(args, "pattern", None)
    
    print(f"Searching history for '{pattern}'...")
    results = search_history(dg_dir, pattern)
    
    if not results:
        print("No matches found.")
        return
        
    for res in results:
        print(f"{res.commit_sha[:7]}:{res.rel_path}:{res.line_num}: {res.content}")
    
    print(f"\nFound {len(results)} match(es).")
