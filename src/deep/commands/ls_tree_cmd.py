"""
deep.commands.ls_tree_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Deep ``ls-tree`` command implementation.
Lists the contents of a tree object.
"""

from __future__ import annotations
from deep.core.errors import DeepCLIException

import sys
from pathlib import Path

from deep.storage.objects import Tree, read_object, Commit
from deep.core.refs import resolve_revision
from deep.core.constants import DEEP_DIR
from deep.core.repository import find_repo


def run(args) -> None:  # type: ignore[no-untyped-def]
    """Execute the ``ls-tree`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Deep: error: {exc}", file=sys.stderr)
        raise DeepCLIException(1)

    dg_dir = repo_root / DEEP_DIR
    objects_dir = dg_dir / "objects"
    
    treeish = args.treeish
    sha = resolve_revision(dg_dir, treeish)
    
    if not sha:
        print(f"Deep: error: revision '{treeish}' not found", file=sys.stderr)
        raise DeepCLIException(1)
        
    obj = read_object(objects_dir, sha)
    
    # If it's a commit, get its tree
    if isinstance(obj, Commit):
        sha = obj.tree_sha
        obj = read_object(objects_dir, sha)
        
    if not isinstance(obj, Tree):
        print(f"Deep: error: object '{treeish}' is not a tree or commit", file=sys.stderr)
        raise DeepCLIException(1)
        
    recursive = getattr(args, "recursive", False)
    _list_tree(objects_dir, obj, "", recursive)


def _list_tree(objects_dir: Path, tree: Tree, prefix: str, recursive: bool) -> None:
    """Helper to list tree entries recursively."""
    for entry in tree.entries:
        mode = entry.mode
        # Deep stores "40000", but Git expects "040000" for CLI output.
        # Ensure we recognize both internally as trees.
        is_directory = mode in ("40000", "040000")
        
        # Consistent display mode (Git-compat)
        display_mode = "040000" if is_directory else mode
        obj_type = "tree" if is_directory else "blob"
        
        path = prefix + entry.name
        
        # Git ls-tree format: <mode> <type> <sha>\t<path>
        print(f"{display_mode} {obj_type} {entry.sha}\t{path}")
        
        if recursive and is_directory:
            sub_tree = read_object(objects_dir, entry.sha)
            if isinstance(sub_tree, Tree):
                _list_tree(objects_dir, sub_tree, path + "/", recursive)
