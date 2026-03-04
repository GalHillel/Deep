"""
deep_git.commands.merge_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deepgit merge <branch>`` command implementation.

Supports:
- "Already up to date" (LCA == target)
- Fast-forward merge (LCA == HEAD)
- Basic 3-way merge with conflict detection
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from deep_git.core.index import Index, IndexEntry, read_index, write_index
from deep_git.core.merge import find_lca, three_way_merge
from deep_git.core.objects import Blob, Commit, Tree, TreeEntry, read_object
from deep_git.core.refs import (
    get_branch,
    get_current_branch,
    resolve_head,
    update_branch,
)
from deep_git.core.repository import DEEP_GIT_DIR, find_repo


def _restore_tree_to_workdir(
    repo_root: Path,
    objects_dir: Path,
    tree: Tree,
    index: Index,
) -> None:
    """Restore a tree's blobs into the working directory and update index."""
    for entry in tree.entries:
        obj = read_object(objects_dir, entry.sha)
        if isinstance(obj, Blob):
            file_path = repo_root / entry.name
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_bytes(obj.data)
            stat = file_path.stat()
            index.entries[entry.name] = IndexEntry(
                sha=entry.sha,
                size=stat.st_size,
                mtime=stat.st_mtime,
            )


def run(args) -> None:  # type: ignore[no-untyped-def]
    """Execute the ``merge`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    dg_dir = repo_root / DEEP_GIT_DIR
    objects_dir = dg_dir / "objects"
    target_branch = args.branch

    # Resolve current HEAD.
    head_sha = resolve_head(dg_dir)
    if head_sha is None:
        print("Error: no commits on current branch.", file=sys.stderr)
        sys.exit(1)

    # Resolve target branch.
    target_sha = get_branch(dg_dir, target_branch)
    if target_sha is None:
        print(f"Error: branch '{target_branch}' not found.", file=sys.stderr)
        sys.exit(1)

    if head_sha == target_sha:
        print("Already up to date.")
        return

    # Find LCA.
    lca_sha = find_lca(objects_dir, head_sha, target_sha)

    # Case 1: LCA == target → already up to date.
    if lca_sha == target_sha:
        print("Already up to date.")
        return

    # Case 2: LCA == HEAD → fast-forward.
    if lca_sha == head_sha:
        current_branch = get_current_branch(dg_dir)
        if current_branch:
            update_branch(dg_dir, current_branch, target_sha)

        # Update working directory.
        target_commit = read_object(objects_dir, target_sha)
        if isinstance(target_commit, Commit):
            tree = read_object(objects_dir, target_commit.tree_sha)
            if isinstance(tree, Tree):
                # Clear current tracked files.
                for rel_path in read_index(dg_dir).entries:
                    full = repo_root / rel_path
                    if full.exists():
                        full.unlink()
                new_index = Index()
                _restore_tree_to_workdir(repo_root, objects_dir, tree, new_index)
                write_index(dg_dir, new_index)

        print(f"Fast-forward merge: {head_sha[:7]}..{target_sha[:7]}")
        return

    # Case 3: True merge — 3-way.
    head_commit = read_object(objects_dir, head_sha)
    target_commit = read_object(objects_dir, target_sha)
    if not isinstance(head_commit, Commit) or not isinstance(target_commit, Commit):
        print("Error: could not read commits.", file=sys.stderr)
        sys.exit(1)

    lca_commit = read_object(objects_dir, lca_sha) if lca_sha else None
    base_tree_sha = lca_commit.tree_sha if isinstance(lca_commit, Commit) else ""

    merged_entries, conflicts = three_way_merge(
        objects_dir,
        base_tree_sha,
        head_commit.tree_sha,
        target_commit.tree_sha,
    )

    if conflicts:
        print(f"CONFLICT in: {', '.join(conflicts)}")
        print("Merge aborted. Please resolve conflicts manually.", file=sys.stderr)
        sys.exit(1)

    # Create merged tree and commit.
    merged_tree = Tree(entries=merged_entries)
    merged_tree_sha = merged_tree.write(objects_dir)

    current_branch = get_current_branch(dg_dir)
    merge_commit = Commit(
        tree_sha=merged_tree_sha,
        parent_shas=[head_sha, target_sha],
        message=f"Merge branch '{target_branch}' into {current_branch or 'HEAD'}",
        timestamp=int(time.time()),
    )
    merge_commit_sha = merge_commit.write(objects_dir)

    if current_branch:
        update_branch(dg_dir, current_branch, merge_commit_sha)

    # Restore merged tree to working dir.
    for rel_path in read_index(dg_dir).entries:
        full = repo_root / rel_path
        if full.exists():
            full.unlink()
    new_index = Index()
    merged_tree_obj = read_object(objects_dir, merged_tree_sha)
    if isinstance(merged_tree_obj, Tree):
        _restore_tree_to_workdir(repo_root, objects_dir, merged_tree_obj, new_index)
    write_index(dg_dir, new_index)

    print(f"Merge made: {merge_commit_sha[:7]}")
