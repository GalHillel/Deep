"""
deep.core.merge
~~~~~~~~~~~~~~~~~~~~~
Merge engine: Lowest Common Ancestor (LCA) detection, fast-forward merges,
and basic 3-way merge with conflict detection.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Set

from deep.storage.objects import Blob, Commit, Tree, TreeEntry, read_object
from deep.core.refs import resolve_head


def _ancestors(objects_dir: Path, start_sha: str) -> set[str]:
    """Return the set of ALL ancestor commit SHAs (inclusive) reachable from *start_sha*."""
    visited: set[str] = set()
    stack = [start_sha]
    while stack:
        sha = stack.pop()
        if sha in visited:
            continue
        visited.add(sha)
        obj = read_object(objects_dir, sha)
        if isinstance(obj, Commit):
            stack.extend(obj.parent_shas)
    return visited


def find_lca(objects_dir: Path, sha_a: str, sha_b: str) -> Optional[str]:
    """Find the Lowest Common Ancestor of two commits.

    Uses a simple BFS approach: compute all ancestors of *sha_a*, then walk
    backwards from *sha_b* until we find a commit in the ancestor set.

    Returns:
        The LCA commit SHA, or ``None`` if there is no common ancestor.
    """
    ancestors_a = _ancestors(objects_dir, sha_a)
    # BFS from sha_b, stop at first ancestor of a.
    queue = [sha_b]
    visited: set[str] = set()
    while queue:
        current = queue.pop(0)
        if current in visited:
            continue
        visited.add(current)
        if current in ancestors_a:
            return current
        obj = read_object(objects_dir, current)
        if isinstance(obj, Commit):
            queue.extend(obj.parent_shas)
    return None


def _tree_entries_map(objects_dir: Path, tree_sha: str | None) -> dict[str, str]:
    """Return {name: blob_sha} for entries in a tree."""
    if not tree_sha:
        return {}
    obj = read_object(objects_dir, tree_sha)
    if not isinstance(obj, Tree):
        return {}
    return {e.name: e.sha for e in obj.entries}


def three_way_merge(
    objects_dir: Path,
    base_tree_sha: str,
    ours_tree_sha: str,
    theirs_tree_sha: str,
) -> tuple[list[TreeEntry], list[str]]:
    """Perform a basic 3-way merge between trees.

    Returns:
        A tuple of ``(merged_entries, conflict_paths)``.
        ``conflict_paths`` lists files that have conflicting changes.
    """
    base = _tree_entries_map(objects_dir, base_tree_sha)
    ours = _tree_entries_map(objects_dir, ours_tree_sha)
    theirs = _tree_entries_map(objects_dir, theirs_tree_sha)

    all_names = sorted(set(base) | set(ours) | set(theirs))
    merged: list[TreeEntry] = []
    conflicts: list[str] = []

    for name in all_names:
        b_sha = base.get(name)
        o_sha = ours.get(name)
        t_sha = theirs.get(name)

        if o_sha == t_sha:
            # Both sides agree (or both deleted).
            if o_sha is not None:
                merged.append(TreeEntry(mode="100644", name=name, sha=o_sha))
            continue

        if o_sha == b_sha:
            # We didn't change it; take theirs.
            if t_sha is not None:
                merged.append(TreeEntry(mode="100644", name=name, sha=t_sha))
            continue

        if t_sha == b_sha:
            # They didn't change it; take ours.
            if o_sha is not None:
                merged.append(TreeEntry(mode="100644", name=name, sha=o_sha))
            continue

        # Both sides changed differently → conflict.
        conflicts.append(name)
        # Keep ours for now.
        if o_sha is not None:
            merged.append(TreeEntry(mode="100644", name=name, sha=o_sha))

    return merged, conflicts
