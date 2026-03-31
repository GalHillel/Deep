"""
deep.commands.inspect_tree_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Internal debug command to verify raw tree entry modes and object types.
"""

import sys
from deep.core.errors import DeepCLIException
from pathlib import Path
from deep.core.repository import find_repo, DEEP_DIR
from deep.storage.objects import read_object, Tree, Blob
from deep.utils.ux import DeepHelpFormatter, format_example
import argparse
from typing import Any


from deep.utils.ux import (
    DeepHelpFormatter, format_header, format_example, format_description
)
import argparse
from typing import Any


def setup_parser(subparsers: Any) -> None:
    """Set up the 'inspect-tree' command parser."""
    p_inspect = subparsers.add_parser(
        "inspect-tree",
        help="Internal: Inspect raw tree entries (debug)",
        description="""Deep Inspect-Tree is a forensic diagnostic tool for verifying the raw entry modes, names, and child object types within a specific tree object.

It is primarily used for debugging repository corruption or verifying low-level storage integrity.""",
        epilog="""

\033[1mEXAMPLES:\033[0m
  \033[1;34m⚓️ deep inspect-tree abc1234\033[0m
     Inspect the raw entries of the tree object with SHA-1 'abc1234'
  \033[1;34m⚓️ deep inspect-tree HEAD^{tree}\033[0m
     Inspect the tree object associated with the current HEAD
""",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    p_inspect.add_argument("sha", help="The SHA-1 hash of the tree object to inspect")

def run(args) -> None:
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Deep: error: {exc}", file=sys.stderr)
        raise DeepCLIException(1)

    dg_dir = repo_root / DEEP_DIR
    objects_dir = dg_dir / "objects"
    sha = args.sha

    try:
        obj = read_object(objects_dir, sha)
    except FileNotFoundError:
        print(f"Deep: error: invalid object SHA '{sha}'", file=sys.stderr)
        raise DeepCLIException(1)
    except ValueError as e:
        print(f"Deep: error: {e}", file=sys.stderr)
        raise DeepCLIException(1)
        
    if not isinstance(obj, Tree):
        print(f"Deep: error: Object {sha} is not a tree ({obj.OBJ_TYPE})", file=sys.stderr)
        raise DeepCLIException(1)
    
    print(f"Tree {sha}:")
    for entry in sorted(obj.entries, key=lambda e: e.name):
        try:
            child = read_object(objects_dir, entry.sha)
            type_str = child.OBJ_TYPE
        except Exception:
            type_str = "MISSING"
        
        print(f"{entry.mode:<6} {entry.name} -> {type_str} ({entry.sha[:7]})")
