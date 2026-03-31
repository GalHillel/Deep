"""
deep.commands.debug_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Debug tooling for inspecting internal Deep state.
"""

from __future__ import annotations
from deep.core.errors import DeepCLIException
import sys
from pathlib import Path

from deep.core.repository import find_repo, DEEP_DIR
from deep.storage.objects import read_object, Tree, Commit
from deep.core.refs import resolve_head
from deep.utils.ux import DeepHelpFormatter, format_example
from typing import Any


def setup_parser(subparsers: Any) -> None:
    """Set up the 'debug-tree' command parser."""
    p_debug = subparsers.add_parser(
        "debug-tree",
        help="Internal: Deep-inspect tree objects recursively",
        description="Forensic tool to verify raw tree entry modes and object types, including hidden characters.",
        epilog=f"""
Examples:
{format_example("deep debug-tree", "Inspect the current head tree including mode details")}
{format_example("deep debug-tree <sha>", "Inspect a specific tree object")}
""",
        formatter_class=DeepHelpFormatter,
    )
    p_debug.add_argument("sha", nargs="?", help="The SHA-1 hash of the tree object to inspect (default: HEAD)")


def run(args) -> None:
    """Implement 'deep debug-tree'."""
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Deep: error: {exc}", file=sys.stderr)
        raise DeepCLIException(1)

    dg_dir = repo_root / DEEP_DIR
    objects_dir = dg_dir / "objects"

    sha = args.sha
    if not sha:
        sha = resolve_head(dg_dir)
        if not sha:
            print("Deep: error: HEAD is not set", file=sys.stderr)
            raise DeepCLIException(1)
        
        # If HEAD is a commit, get its tree
        obj = read_object(objects_dir, sha)
        if isinstance(obj, Commit):
            sha = obj.tree_sha
            print(f"Inspecting tree for HEAD ({sha[:8]}):")

    def dump_tree(tree_sha: str, indent: str = ""):
        obj = read_object(objects_dir, tree_sha)
        if not isinstance(obj, Tree):
            print(f"{indent}Error: {tree_sha} is not a tree object ({type(obj).__name__})")
            return

        for entry in obj.entries:
            # Phase 7: Use repr() to make hidden characters visible
            name_display = repr(entry.name)
            print(f"{indent}{entry.mode} {entry.sha[:8]} {name_display}")
            
            # Recurse if it's a directory
            if entry.mode == "40000":
                dump_tree(entry.sha, indent + "  ")

    dump_tree(sha)
