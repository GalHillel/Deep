"""
deep.commands.show_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Deep ``show`` command implementation.
Shows commit metadata and the diff of the changes.
"""

from __future__ import annotations
from deep.core.errors import DeepCLIException

import sys
from pathlib import Path

from deep.storage.objects import Commit, read_object, Tree, Tag
from deep.core.refs import resolve_revision
from deep.core.constants import DEEP_DIR
from deep.core.repository import find_repo
from deep.utils.ux import (
    DeepHelpFormatter, format_header, format_example, format_description
)
from typing import Any


def setup_parser(subparsers: Any) -> None:
    """Set up the 'show' command parser."""
    p_show = subparsers.add_parser(
        "show",
        help="Display various types of objects",
        description=format_description("Show detailed information, content, and metadata for Deep objects (commits, tags, trees, and blobs). For commits, this command displays the author, date, message, and a colorized diff of the changes relative to its parent."),
        epilog=f"""
{format_header("Examples")}
{format_example("deep show HEAD", "Show the most recent commit and its colorized diff")}
{format_example("deep show v1.0.2", "Display metadata and target object for a specific tag")}
{format_example("deep show abc1234:src/main.py", "Show the contents of a specific file in a commit")}
{format_example("deep show --stat", "Show only the modification statistics for the object")}
""",
        formatter_class=DeepHelpFormatter,
    )
    p_show.add_argument("object", nargs="?", default="HEAD", help="The object identifier to show (default: HEAD)")
from deep.utils.ux import Color
from deep.utils.utils import format_date


def run(args) -> None:  # type: ignore[no-untyped-def]
    """Execute the ``show`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Deep: error: {exc}", file=sys.stderr)
        raise DeepCLIException(1)

    dg_dir = repo_root / DEEP_DIR
    objects_dir = dg_dir / "objects"
    
    obj_name = getattr(args, "object", "HEAD")
    sha = resolve_revision(dg_dir, obj_name)
    
    if not sha:
        print(f"Deep: error: object '{obj_name}' not found", file=sys.stderr)
        raise DeepCLIException(1)
        
    obj = read_object(objects_dir, sha)
    
    if isinstance(obj, Commit):
        # 1. Print Commit Metadata (like log)
        print(Color.wrap(Color.YELLOW, f"commit {sha}"))
        print(f"{Color.wrap(Color.BOLD, 'Author:')} {obj.author}")
        date_str = format_date(obj.timestamp, obj.timezone)
        print(f"{Color.wrap(Color.BOLD, 'Date:')}   {date_str}")
        print()
        for line in obj.message.splitlines():
            print(f"    {line}")
        print()
        
        # 2. Show Diff against first parent (or empty if first commit)
        from deep.core.diff import diff_trees
        if obj.parent_shas:
            parent_sha = obj.parent_shas[0]
            diffs = diff_trees(dg_dir, parent_sha, sha)
            _render_diffs(diffs)
        else:
            # First commit: diff against empty tree
            # Collect all files in this commit's tree and show them as additions
            from deep.core.diff import _get_tree_entries_recursive, diff_blobs
            tree_files = _get_tree_entries_recursive(dg_dir / "objects", obj.tree_sha)
            diffs = []
            for path in sorted(tree_files.keys()):
                res = diff_blobs(dg_dir / "objects", None, tree_files[path], path)
                if res:
                    diffs.append((path, res))
            _render_diffs(diffs)
    elif isinstance(obj, Tag):
        print(f"tag {obj.name}")
        print(f"Tagger: {obj.tagger}")
        print(f"Date:   {format_date(obj.timestamp, obj.timezone)}")
        print()
        print(obj.message)
        print()
        # Optionally show the object it points to
    else:
        # Just show raw type/content for other objects
        print(f"object {sha}")
        print(f"type: {obj.get_type()}")


def _render_diffs(diffs: list[tuple[str, str]]) -> None:
    """Render diff output with colors."""
    for rel_path, diff_text in diffs:
        print(f"\033[1;36mdiff --deep a/{rel_path} b/{rel_path}\033[0m")
        for line in diff_text.splitlines():
            if line.startswith("+++") or line.startswith("---"):
                print(f"\033[1;36m{line}\033[0m")
            elif line.startswith("+"):
                print(f"\033[32m{line}\033[0m")
            elif line.startswith("-"):
                print(f"\033[31m{line}\033[0m")
            elif line.startswith("@@"):
                print(f"\033[33m{line}\033[0m")
            else:
                print(line)
