"""
deep.core.merge
~~~~~~~~~~~~~~~~~~~~~
Merge engine: Lowest Common Ancestor (LCA) detection, fast-forward merges,
and basic 3-way merge with conflict detection.
"""

from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import Optional, Set

import heapq
import time
from deep.storage.objects import Blob, Commit, Tree, TreeEntry, read_object, write_object
from deep.core.refs import resolve_head
from deep.utils.utils import hash_bytes
from deep.storage.commit_graph import CommitGraph

def find_all_lcas(objects_dir: Path, sha_a: str, sha_b: str) -> list[str]:
    """Find all Lowest Common Ancestors of two commits.
    
    If multiple LCAs exist (criss-cross), return all of them.
    Only returns LCAs that are not ancestors of other LCAs.
    """
    if sha_a == sha_b:
        return [sha_a]

    # 1. Gather all common ancestors
    candidates = []
    
    dg_dir = objects_dir.parent
    cg = CommitGraph(dg_dir)
    use_cg = cg.load()

    def get_ancestors_cg(sha: str) -> set[str]:
        anc = {sha}
        idx = cg.get_commit_index(sha)
        if idx is None: return get_ancestors_loose(sha)
        
        queue = [idx]
        visited_indices = {idx}
        while queue:
            curr_idx = queue.pop()
            info = cg.get_commit_info(curr_idx)
            if not info: continue
            _, parents, _, _ = info
            for p_idx in parents:
                if p_idx not in visited_indices:
                    visited_indices.add(p_idx)
                    anc.add(cg._oids[p_idx].hex())
                    queue.append(p_idx)
        return anc

    def get_ancestors_loose(sha: str) -> set[str]:
        anc = {sha}
        stack = [sha]
        while stack:
            curr = stack.pop()
            try:
                obj = read_object(objects_dir, curr)
                if isinstance(obj, Commit):
                    for p in obj.parent_shas:
                        if p not in anc:
                            anc.add(p)
                            stack.append(p)
            except Exception: pass
        return anc

    if use_cg:
        anc_a = get_ancestors_cg(sha_a)
        anc_b = get_ancestors_cg(sha_b)
    else:
        anc_a = get_ancestors_loose(sha_a)
        anc_b = get_ancestors_loose(sha_b)
    common = anc_a.intersection(anc_b)
    
    if not common:
        return []

    # 2. Filter out candidates that are ancestors of other candidates
    lcas = []
    for c in common:
        is_lca = True
        for other in common:
            if c == other: continue
            # If c is an ancestor of other, it's not an LCA
            # Using optimized check if possible
            if use_cg:
                anc_other = get_ancestors_cg(other)
            else:
                anc_other = get_ancestors_loose(other)
                
            if c in anc_other:
                is_lca = False
                break
        if is_lca:
            lcas.append(c)
            
    return lcas


def find_lca(objects_dir: Path, sha_a: str, sha_b: str) -> Optional[str]:
    """Compatibility wrapper that returns the first LCA found."""
    lcas = find_all_lcas(objects_dir, sha_a, sha_b)
    return lcas[0] if lcas else None


def _tree_entries_map_full(objects_dir: Path, tree_sha: str | None) -> dict[str, TreeEntry]:
    """Return {name: TreeEntry} for entries in a tree."""
    if not tree_sha:
        return {}
    obj = read_object(objects_dir, tree_sha)
    if not isinstance(obj, Tree):
        return {}
    return {e.name: e for e in obj.entries}


def three_way_merge(
    objects_dir: Path,
    base_tree_sha: str | None,
    ours_tree_sha: str | None,
    theirs_tree_sha: str | None,
    path: str = ""
) -> tuple[str, list[str]]:
    """Recursively perform a 3-way merge between trees.
    
    Returns:
        A tuple of (merged_tree_sha, conflict_paths).
    """
    base = _tree_entries_map_full(objects_dir, base_tree_sha)
    ours = _tree_entries_map_full(objects_dir, ours_tree_sha)
    theirs = _tree_entries_map_full(objects_dir, theirs_tree_sha)

    all_names = sorted(set(base) | set(ours) | set(theirs))
    merged_entries: list[TreeEntry] = []
    conflicts: list[str] = []

    for name in all_names:
        b = base.get(name)
        o = ours.get(name)
        t = theirs.get(name)
        
        full_path = f"{path}/{name}" if path else name

        b_sha = b.sha if b else None
        o_sha = o.sha if o else None
        t_sha = t.sha if t else None
        
        # 1. Trivial cases
        if o_sha == t_sha:
            if o: merged_entries.append(o)
            continue
        if o_sha == b_sha:
            if t: merged_entries.append(t)
            continue
        if t_sha == b_sha:
            if o: merged_entries.append(o)
            continue
            
        # 2. Both changed. Check if both are trees.
        o_is_tree = o and o.mode == "040000"
        t_is_tree = t and t.mode == "040000"
        b_is_tree = b and b.mode == "040000"
        
        if o_is_tree and t_is_tree:
            # Recursive tree merge
            res_sha, res_conflicts = three_way_merge(
                objects_dir, b_sha if b_is_tree else None, o_sha, t_sha, full_path
            )
            merged_entries.append(TreeEntry(name=name, mode="040000", sha=res_sha))
            conflicts.extend(res_conflicts)
        else:
            # File conflict or File/Tree conflict
            conflicts.append(full_path)
            # Default to 'ours' but we could do more (e.g. text merge)
            if o: merged_entries.append(o)

    merged_tree = Tree(entries=merged_entries)
    merged_sha = merged_tree.write(objects_dir)
    return merged_sha, conflicts


def recursive_merge(objects_dir: Path, sha_a: str, sha_b: str) -> tuple[str, list[str]]:
    """Advanced merge strategy: resolves criss-cross merges and recurses into trees.
    
    Returns:
        (merged_tree_sha, conflict_paths)
    """
    lcas = find_all_lcas(objects_dir, sha_a, sha_b)
    
    if not lcas:
        # No common ancestor, merge against empty tree
        base_tree = None
    elif len(lcas) == 1:
        base_tree = read_object(objects_dir, lcas[0]).tree_sha
    else:
        # Multiple LCAs! Recursive merge them into a virtual base.
        print(f"DeepBridge: Recursive merge for {len(lcas)} LCAs...")
        
        # Merge first two LCAs
        v_tree, _ = recursive_merge(objects_dir, lcas[0], lcas[1])
        v_commit = Commit(tree_sha=v_tree, parent_shas=[lcas[0], lcas[1]], message="virtual base", timestamp=int(time.time()))
        v_sha = v_commit.write(objects_dir)
        
        # Merge remaining LCAs
        for i in range(2, len(lcas)):
            v_tree, _ = recursive_merge(objects_dir, v_sha, lcas[i])
            v_commit = Commit(tree_sha=v_tree, parent_shas=[v_sha, lcas[i]], message="virtual base", timestamp=int(time.time()))
            v_sha = v_commit.write(objects_dir)
            
        base_tree = v_tree

    ours = read_object(objects_dir, sha_a)
    theirs = read_object(objects_dir, sha_b)
    
    return three_way_merge(objects_dir, base_tree, ours.tree_sha, theirs.tree_sha)
