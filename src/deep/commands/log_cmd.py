"""
deep.commands.log_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~
DeepGit ``log`` command implementation.
"""

from __future__ import annotations

import sys
from pathlib import Path

from deep.storage.objects import Commit, read_object
from deep.core.refs import get_commit_decorations, log_history, resolve_head
from deep.core.repository import DEEP_DIR, find_repo
from deep.utils.ux import Color
from deep.utils.utils import format_date


def run(args) -> None:  # type: ignore[no-untyped-def]
    """Execute the ``log`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"DeepGit: error: {exc}", file=sys.stderr)
        sys.exit(1)

    dg_dir = repo_root / DEEP_DIR
    objects_dir = dg_dir / "objects"

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
