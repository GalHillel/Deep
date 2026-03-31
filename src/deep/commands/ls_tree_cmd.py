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
        obj_type = "tree" if mode == "040000" else "blob"
        path = prefix + entry.name
        
        # Git ls-tree format: <mode> <type> <sha> <path>
        print(f"{mode} {obj_type} {entry.sha}    {path}")
        
        if recursive and obj_type == "tree":
            sub_tree = read_object(objects_dir, entry.sha)
            if isinstance(sub_tree, Tree):
                _list_tree(objects_dir, sub_tree, path + "/", recursive)
