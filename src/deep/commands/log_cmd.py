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
from deep.core.refs import get_commit_decorations, log_history, resolve_head, resolve_revision
from deep.core.constants import DEEP_DIR
from deep.core.repository import find_repo
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

    start_sha = None
    exclude_shas = set()

    revisions = getattr(args, "revisions", [])
    if revisions:
        rev = revisions[0]
        if ".." in rev:
            left, right = rev.split("..", 1)
            left_sha = resolve_revision(dg_dir, left if left else "HEAD")
            right_sha = resolve_revision(dg_dir, right if right else "HEAD")
            if not left_sha or not right_sha:
                print(f"Deep: error: Invalid revision range {rev}", file=sys.stderr)
                raise DeepCLIException(1)
            
            # exclude ancestors of left_sha
            exclude_shas = set(log_history(dg_dir, left_sha))
            start_sha = right_sha
        else:
            start_sha = resolve_revision(dg_dir, rev)
            if not start_sha:
                print(f"Deep: error: unknown revision {rev}", file=sys.stderr)
                raise DeepCLIException(1)

    max_count = getattr(args, "max_count", None)

    if getattr(args, "graph", False):
        from deep.core.graph import get_history_graph, render_graph
        graph_max_count = max_count if max_count is not None else 100
        nodes = get_history_graph(dg_dir, start_sha=start_sha, max_count=graph_max_count, exclude_shas=exclude_shas)
        if not nodes:
            print("No commits yet.")
        else:
            render_graph(nodes)
        return

    shas = log_history(dg_dir, start_sha=start_sha)
    if exclude_shas:
        shas = [s for s in shas if s not in exclude_shas]
    if not shas:
        print("No commits yet.")
        return

    if max_count is not None:
        shas = shas[:max_count]

    decs = get_commit_decorations(dg_dir)

    for sha in shas:
        try:
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
                
                # Render Merge parents if a merge commit
                if len(obj.parent_shas) > 1:
                    parent_display = " ".join(p[:7] for p in obj.parent_shas)
                    print(f"{graph_pad}{Color.wrap(Color.BOLD, 'Merge:')}  {parent_display}")

                print(f"{graph_pad}{Color.wrap(Color.BOLD, 'Author:')} {obj.author}")
                date_str = format_date(obj.timestamp, obj.timezone)
                print(f"{graph_pad}{Color.wrap(Color.BOLD, 'Date:')}   {date_str}")
                print(graph_pad.rstrip())
                for line in obj.message.splitlines():
                    print(f"{graph_pad}    {line}")
                print(graph_pad.rstrip())
        except (FileNotFoundError, ValueError):
            # Stop log if we hit a boundary (missing object) in a shallow clone
            break
        except Exception as e:
            print(f"Deep: error during log: {e}", file=sys.stderr)
            raise DeepCLIException(1)
