"""
deep.commands.fsck_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep fsck`` — Verify the integrity of the reachable objects, trees, commits, and references.
"""

from __future__ import annotations

import sys
from pathlib import Path

from deep.core.repository import DEEP_GIT_DIR, find_repo
from deep.core.refs import list_branches, list_tags, resolve_head, get_branch, get_tag
from deep.storage.objects import read_object, Commit, Tree, Tag, Blob


def run(args) -> None:
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    dg_dir = repo_root / DEEP_GIT_DIR
    objects_dir = dg_dir / "objects"

    errors = 0
    checked_commits = set()
    checked_trees = set()
    checked_blobs = set()

    print("Checking reference consistency...")
    # 1. Reference consistency
    heads = {}
    for b in list_branches(dg_dir):
        sha = get_branch(dg_dir, b)
        if sha:
            try:
                obj = read_object(objects_dir, sha)
                if not isinstance(obj, Commit):
                    print(f"Error: Branch '{b}' points to non-commit object {sha[:7]}")
                    errors += 1
                heads[b] = sha
            except Exception as e:
                print(f"Error: Branch '{b}' points to missing object {sha[:7]} ({e})")
                errors += 1

    for t in list_tags(dg_dir):
        sha = get_tag(dg_dir, t)
        if sha:
            try:
                obj = read_object(objects_dir, sha)
                if not isinstance(obj, Tag):
                    print(f"Error: Tag '{t}' points to non-tag object {sha[:7]}")
                    errors += 1
                else:
                    target_sha = obj.target_sha
                    try:
                        read_object(objects_dir, target_sha)
                    except Exception:
                        print(f"Error: Tag '{t}' target object {target_sha[:7]} is missing")
                        errors += 1
            except Exception as e:
                print(f"Error: Tag '{t}' points to missing object {sha[:7]} ({e})")
                errors += 1

    head_sha = resolve_head(dg_dir)
    if head_sha:
        try:
            read_object(objects_dir, head_sha)
            heads["HEAD"] = head_sha
        except Exception:
            print(f"Error: HEAD points to missing object {head_sha[:7]}")
            errors += 1

    print("Checking commit DAG, tree references, and object existence...")
    # 2. Commit DAG & Trees
    queue = list(heads.values())
    
    while queue:
        sha = queue.pop(0)
        if sha in checked_commits:
            continue
        try:
            obj = read_object(objects_dir, sha)
            if isinstance(obj, Commit):
                checked_commits.add(sha)
                
                # Check parents exist
                for p_sha in obj.parent_shas:
                    try:
                        read_object(objects_dir, p_sha)
                        queue.append(p_sha)
                    except Exception:
                        print(f"Error: Commit {sha[:7]} parent {p_sha[:7]} is missing")
                        errors += 1
                
                # Check tree exists
                t_sha = obj.tree_sha
                if t_sha:
                    try:
                        read_object(objects_dir, t_sha)
                        # Add tree to validation queue
                        queue.append(t_sha)
                    except Exception:
                        print(f"Error: Commit {sha[:7]} tree {t_sha[:7]} is missing")
                        errors += 1
            
            elif isinstance(obj, Tree):
                if sha in checked_trees:
                    continue
                checked_trees.add(sha)
                
                for entry in obj.entries:
                    e_sha = entry.sha
                    try:
                        child = read_object(objects_dir, e_sha)
                        if isinstance(child, Tree):
                            if entry.mode != "40000":
                                print(f"Error: Tree {sha[:7]} entry '{entry.name}' is a tree but has mode {entry.mode}")
                                errors += 1
                            if e_sha not in checked_trees:
                                queue.append(e_sha)
                        elif isinstance(child, Blob):
                            if entry.mode == "40000":
                                print(f"Error: Tree {sha[:7]} entry '{entry.name}' is a blob but has mode 40000")
                                errors += 1
                            checked_blobs.add(e_sha)
                    except Exception:
                        print(f"Error: Tree {sha[:7]} entry '{entry.name}' points to missing object {e_sha[:7]}")
                        errors += 1

        except Exception as e:
            # Reached a missing object in the queue
            pass

    print(f"\nFsck completed.")
    print(f"Checked: {len(checked_commits)} commits, {len(checked_trees)} trees, {len(checked_blobs)} blobs.")
    if errors == 0:
        print("Result: OK - No corruption found.")
    else:
        print(f"Result: FAILED - {errors} error(s) found.")
        sys.exit(1)
