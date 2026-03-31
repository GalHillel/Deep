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
from deep.utils.ux import (
    DeepHelpFormatter, format_header, format_example, format_description
)
import argparse
from typing import Any


def setup_parser(subparsers: Any) -> None:
    """Set up the 'debug' command parser."""
    p_debug = subparsers.add_parser(
        "debug",
        help="Internal diagnostics and forensic tools",
        description="""Access internal Deep diagnostic tools.

These commands are intended for developers and power users to inspect the raw state of the repository database and verify internal consistency at the lowest level.""",
        epilog="""

\033[1mEXAMPLES:\033[0m
  \033[1;34m⚓️ deep debug tree\033[0m
     Inspect the current HEAD tree object recursively
  \033[1;34m⚓️ deep debug tree <sha>\033[0m
     Inspect a specific tree object by its SHA-1 hash
  \033[1;34m⚓️ deep debug objects\033[0m
     List all objects in the database with their raw types
""",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    rs = p_debug.add_subparsers(dest="debug_command", metavar="ACTION")
    
    p_tree = rs.add_parser("tree", help="Inspect a tree object recursively")
    p_tree.add_argument("sha", nargs="?", help="The SHA-1 hash of the tree object to inspect (default: HEAD)")


def run(args) -> None:
    """Implement 'deep debug' commands."""
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Deep: error: {exc}", file=sys.stderr)
        raise DeepCLIException(1)

    dg_dir = repo_root / DEEP_DIR
    objects_dir = dg_dir / "objects"
    
    cmd = getattr(args, "debug_command", "tree")

    if cmd == "tree":
        sha = getattr(args, "sha", None)
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
