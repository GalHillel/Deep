"""
deep_git.commands.doctor_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deepgit doctor`` command implementation.

Verifies the integrity of the repository: refs, index, and objects.
"""

from __future__ import annotations

import os
import sys
import zlib
from pathlib import Path

from deep_git.core.index import read_index
from deep_git.core.objects import Blob, Commit, Tag, Tree, read_object
from deep_git.core.refs import list_branches, resolve_head, list_tags, get_tag, get_branch
from deep_git.core.repository import DEEP_GIT_DIR, find_repo
from deep_git.core.utils import Color


def run(args) -> None:  # type: ignore[no-untyped-def]
    """Execute the ``doctor`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    dg_dir = repo_root / DEEP_GIT_DIR
    objects_dir = dg_dir / "objects"
    
    errors = 0
    warnings = 0

    print("Checking object database...")
    # Iterate objects
    seen_objects = 0
    if objects_dir.exists():
        for root, dirs, files in os.walk(objects_dir):
            for file in files:
                # Expecting layout like objects/aa/bbcccc
                if len(Path(root).name) == 2 and len(file) == 38:
                    sha = Path(root).name + file
                    seen_objects += 1
                    try:
                        obj = read_object(objects_dir, sha)
                        if isinstance(obj, Commit):
                            for p_sha in obj.parent_shas:
                                try:
                                    read_object(objects_dir, p_sha)
                                except Exception:
                                    print(Color.wrap(Color.RED, f"Error: Commit {sha[:7]} references missing parent {p_sha[:7]}"))
                                    errors += 1
                            try:
                                read_object(objects_dir, obj.tree_sha)
                            except Exception:
                                print(Color.wrap(Color.RED, f"Error: Commit {sha[:7]} references missing tree {obj.tree_sha[:7]}"))
                                errors += 1
                        elif isinstance(obj, Tree):
                            for entry in obj.entries:
                                try:
                                    read_object(objects_dir, entry.sha)
                                except Exception:
                                    print(Color.wrap(Color.RED, f"Error: Tree {sha[:7]} references missing blob/tree {entry.sha[:7]}"))
                                    errors += 1
                        elif isinstance(obj, Tag):
                            try:
                                read_object(objects_dir, obj.target_sha)
                            except Exception:
                                print(Color.wrap(Color.RED, f"Error: Tag object {sha[:7]} references missing target {obj.target_sha[:7]}"))
                                errors += 1
                    except FileNotFoundError:
                        print(Color.wrap(Color.RED, f"Error: Object {sha} is corrupt or unreadable"))
                        errors += 1
                    except zlib.error:
                        print(Color.wrap(Color.RED, f"Error: Object {sha} has zlib decompression errors"))
                        errors += 1
                    except Exception as e:
                        print(Color.wrap(Color.RED, f"Error: Object {sha} failed to parse: {e}"))
                        errors += 1

    print(f"Verified {seen_objects} objects.")
    
    print("Checking references...")
    branches = list_branches(dg_dir)
    for b in branches:
        sha = get_branch(dg_dir, b)
        if sha:
            try:
                read_object(objects_dir, sha)
            except Exception:
                print(Color.wrap(Color.RED, f"Error: Branch '{b}' points to missing commit {sha[:7]}"))
                errors += 1
    
    tags = list_tags(dg_dir)
    for t in tags:
        sha = get_tag(dg_dir, t)
        if sha:
            try:
                obj = read_object(objects_dir, sha)
                # If annotated tag, check its target too
                if isinstance(obj, Tag):
                    try:
                        read_object(objects_dir, obj.target_sha)
                    except Exception:
                        print(Color.wrap(Color.RED, f"Error: Tag '{t}' points to missing target {obj.target_sha[:7]}"))
                        errors += 1
            except Exception:
                print(Color.wrap(Color.RED, f"Error: Tag '{t}' points to missing object {sha[:7]}"))
                errors += 1

    head_sha = resolve_head(dg_dir)
    if head_sha:
        try:
            read_object(objects_dir, head_sha)
        except Exception:
            print(Color.wrap(Color.RED, f"Error: HEAD points to missing commit {head_sha[:7]}"))
            errors += 1
    else:
        print(Color.wrap(Color.YELLOW, "Warning: HEAD is unborn or missing"))
        warnings += 1

    print("Checking index...")
    try:
        index = read_index(dg_dir)
        for path, entry in index.entries.items():
            try:
                read_object(objects_dir, entry.sha)
            except Exception:
                print(Color.wrap(Color.RED, f"Error: Index entry '{path}' references missing blob {entry.sha[:7]}"))
                errors += 1
    except Exception as e:
        print(Color.wrap(Color.RED, f"Error: Could not read index: {e}"))
        errors += 1
        
    print()
    if errors == 0:
        if warnings == 0:
            print(Color.wrap(Color.GREEN, "Repository is clean and consistent. 0 errors."))
        else:
            print(Color.wrap(Color.YELLOW, f"Repository is consistent. 0 errors, {warnings} warnings."))
    else:
        print(Color.wrap(Color.RED, f"Repository integrity compromised. Found {errors} errors, {warnings} warnings."))
        sys.exit(1)
