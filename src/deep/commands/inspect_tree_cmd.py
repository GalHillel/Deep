"""
deep.commands.inspect_tree_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Internal debug command to verify raw tree entry modes and object types.
"""

import sys
from pathlib import Path
from deep.core.constants import DEEP_DIR
from deep.core.repository import find_repo
from deep.storage.objects import read_object, Tree, Blob

def run(args) -> None:
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Deep: error: {exc}", file=sys.stderr)
        sys.exit(1)

    dg_dir = repo_root / DEEP_DIR
    objects_dir = dg_dir / "objects"
    sha = args.sha

    try:
        obj = read_object(objects_dir, sha)
        if not isinstance(obj, Tree):
            print(f"Deep: error: Object {sha} is not a tree ({obj.OBJ_TYPE})", file=sys.stderr)
            sys.exit(1)
        
        print(f"Tree {sha}:")
        for entry in sorted(obj.entries, key=lambda e: e.name):
            try:
                child = read_object(objects_dir, entry.sha)
                type_str = child.OBJ_TYPE
            except Exception:
                type_str = "MISSING"
            
            print(f"{entry.mode:<6} {entry.name} -> {type_str} ({entry.sha[:7]})")
            
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
