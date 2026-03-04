"""
deep_git.commands.rebase_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deepgit rebase <branch>`` command implementation.

Performs a linear rewrite of local commits on top of <branch>.
"""

from __future__ import annotations

import sys
from pathlib import Path

from deep_git.commands.merge_cmd import _restore_tree_to_workdir
from deep_git.core.index import Index, IndexEntry, read_index, write_index
from deep_git.core.merge import find_lca, three_way_merge
from deep_git.core.objects import Commit, Tree, read_object
from deep_git.core.refs import (
    get_branch,
    get_current_branch,
    resolve_head,
    update_branch,
    update_head,
)
from deep_git.core.repository import DEEP_GIT_DIR, find_repo


def run(args) -> None:  # type: ignore[no-untyped-def]
    """Execute the ``rebase`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    dg_dir = repo_root / DEEP_GIT_DIR
    objects_dir = dg_dir / "objects"
    target_branch = args.branch

    # Resolve head and target branch
    head_sha = resolve_head(dg_dir)
    if not head_sha:
        print("Error: no commits on current branch.", file=sys.stderr)
        sys.exit(1)

    target_sha = get_branch(dg_dir, target_branch)
    if not target_sha:
        print(f"Error: branch '{target_branch}' not found.", file=sys.stderr)
        sys.exit(1)

    if head_sha == target_sha:
        print("Current branch is up to date.")
        return

    from deep_git.core.status import compute_status
    status = compute_status(repo_root)
    if status.staged_new or status.staged_modified or status.staged_deleted or status.modified or status.deleted:
        print("Error: working directory not clean.", file=sys.stderr)
        print("Please commit or stash your changes before rebasing.", file=sys.stderr)
        sys.exit(1)

    lca_sha = find_lca(objects_dir, head_sha, target_sha)

    # If LCA == head_sha, it's a fast-forward!
    if lca_sha == head_sha:
        print(f"Fast-forwarded to {target_branch}.")
        curr_branch = get_current_branch(dg_dir)
        if curr_branch:
            update_branch(dg_dir, curr_branch, target_sha)
        
        target_commit = read_object(objects_dir, target_sha)
        assert isinstance(target_commit, Commit)
        tree = read_object(objects_dir, target_commit.tree_sha)
        assert isinstance(tree, Tree)
        
        for rel_path in read_index(dg_dir).entries:
            full = repo_root / rel_path
            if full.exists():
                full.unlink()
        new_index = Index()
        _restore_tree_to_workdir(repo_root, objects_dir, tree, new_index)
        write_index(dg_dir, new_index)
        return

    if lca_sha == target_sha:
        print(f"Current branch is up to date.")
        return

    # Gather commits from head back to LCA
    # Read linearly
    commits_to_apply: list[str] = []
    curr = head_sha
    while curr and curr != lca_sha:
        commits_to_apply.append(curr)
        c_obj = read_object(objects_dir, curr)
        assert isinstance(c_obj, Commit)
        if not c_obj.parent_shas:
            break
        curr = c_obj.parent_shas[0]

    commits_to_apply.reverse()

    # Rebase onto target_sha
    curr_head = target_sha
    
    for commit_sha in commits_to_apply:
        c_obj = read_object(objects_dir, commit_sha)
        assert isinstance(c_obj, Commit)
        
        parent_sha = c_obj.parent_shas[0] if c_obj.parent_shas else ""
        parent_tree = ""
        if parent_sha:
            p_obj = read_object(objects_dir, parent_sha)
            assert isinstance(p_obj, Commit)
            parent_tree = p_obj.tree_sha
            
        curr_head_obj = read_object(objects_dir, curr_head)
        assert isinstance(curr_head_obj, Commit)
        curr_tree = curr_head_obj.tree_sha
        
        commit_tree = c_obj.tree_sha
        
        merged_entries, conflicts = three_way_merge(
            objects_dir, parent_tree, curr_tree, commit_tree
        )
        
        if conflicts:
            print(f"CONFLICT applying commit {commit_sha[:7]}: {c_obj.message}", file=sys.stderr)
            print("Rebase aborted. Conflict resolution not supported yet.", file=sys.stderr)
            sys.exit(1)
            
        merged_tree = Tree(entries=merged_entries)
        merged_tree_sha = merged_tree.write(objects_dir)
        
        new_commit = Commit(
            tree_sha=merged_tree_sha,
            parent_shas=[curr_head],
            author=c_obj.author,
            committer=c_obj.committer,
            message=c_obj.message,
            timestamp=c_obj.timestamp,
            timezone=getattr(c_obj, "timezone", "+0000"),
        )
        curr_head = new_commit.write(objects_dir)
        print(f"Applying: {c_obj.message}")
        
    # Update branch pointer and checkout
    curr_branch = get_current_branch(dg_dir)
    if curr_branch:
        update_branch(dg_dir, curr_branch, curr_head)
    else:
        update_head(dg_dir, curr_head)
        
    # Restore working directory
    target_commit = read_object(objects_dir, curr_head)
    assert isinstance(target_commit, Commit)
    tree = read_object(objects_dir, target_commit.tree_sha)
    assert isinstance(tree, Tree)
    
    for rel_path in read_index(dg_dir).entries:
        full = repo_root / rel_path
        if full.exists():
            full.unlink()
    new_index = Index()
    _restore_tree_to_workdir(repo_root, objects_dir, tree, new_index)
    write_index(dg_dir, new_index)
    
    print(f"Successfully rebased and updated {curr_branch or 'HEAD'}.")
