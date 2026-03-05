"""
deep.core.graph
~~~~~~~~~~~~~~~~~~~~
Core graph traversal and rendering for history visualization.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from deep.storage.objects import Commit, read_object
from deep.core.refs import list_branches, list_tags, resolve_head, get_branch, get_tag

@dataclass
class GraphNode:
    sha: str
    commit: Commit
    parents: List[str]
    column: int = 0
    branches: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    message: str = ""

def get_history_graph(dg_dir: Path, max_count: int = 100, all_refs: bool = False) -> List[GraphNode]:
    """Traverse commits and build a graph structure for rendering."""
    objects_dir = dg_dir / "objects"
    
    # Identify entry points
    heads: Dict[str, str] = {}
    if all_refs:
        for b in list_branches(dg_dir):
            sha = get_branch(dg_dir, b)
            if sha:
                heads[b] = sha
    else:
        head_sha = resolve_head(dg_dir)
        if head_sha:
            heads["HEAD"] = head_sha
            
    tags_map: Dict[str, str] = {}
    for t in list_tags(dg_dir):
        sha = get_tag(dg_dir, t)
        if sha:
            tags_map[t] = sha
    
    # Collect nodes using BFS/DFS
    nodes: Dict[str, GraphNode] = {}
    # Use a set for initial queue to avoid duplicates
    queue = list(set(heads.values()))
    queue.sort(reverse=True) # Probabilistic newest first
    processed = set()
    
    while queue and len(nodes) < max_count:
        sha = queue.pop(0)
        if sha in processed:
            continue
        processed.add(sha)
        
        try:
            commit = read_object(objects_dir, sha)
            if not isinstance(commit, Commit):
                continue
                
            node = GraphNode(
                sha=sha,
                commit=commit,
                parents=commit.parent_shas,
                message=commit.message.split("\n")[0][:50]
            )
            
            # Add decorations
            for b_name, b_sha in heads.items():
                if b_sha == sha:
                    node.branches.append(b_name)
            for t_name, t_sha in tags_map.items():
                if t_sha == sha:
                    node.tags.append(t_name)
                    
            nodes[sha] = node
            
            for p_sha in commit.parent_shas:
                if p_sha not in processed:
                    queue.append(p_sha)
                    # Re-sort to maintain chronological-ish order
                    queue.sort(reverse=True)
        except Exception:
            continue
            
    # Sort nodes by timestamp descending
    sorted_nodes = sorted(nodes.values(), key=lambda n: n.commit.timestamp, reverse=True)
    
    # Assign columns (swimlanes)
    active_columns: List[Optional[str]] = []
    
    for node in sorted_nodes:
        # If this SHA is already in a column (from a child), use it
        if node.sha in active_columns:
            node.column = active_columns.index(node.sha)
        else:
            # New thread
            if None in active_columns:
                node.column = active_columns.index(None)
                active_columns[node.column] = node.sha
            else:
                node.column = len(active_columns)
                active_columns.append(node.sha)
        
        # Update columns for parents
        first_parent_assigned = False
        current_sha = active_columns[node.column]
        
        # Remove self from active columns
        active_columns[node.column] = None
        
        for p_sha in node.parents:
            if not first_parent_assigned:
                # First parent takes the current column
                active_columns[node.column] = p_sha
                first_parent_assigned = True
            else:
                # Other parents (merges) need new columns
                if p_sha not in active_columns:
                    if None in active_columns:
                        idx = active_columns.index(None)
                        active_columns[idx] = p_sha
                    else:
                        active_columns.append(p_sha)
                        
    return sorted_nodes

def render_graph(nodes: List[GraphNode]) -> None:
    """Render the graph nodes using Unicode decorations."""
    # Colors (ANSI)
    C_SHA = "\033[33m" # Yellow
    C_BRANCH = "\033[32m" # Green
    C_TAG = "\033[35m" # Magenta
    C_RESET = "\033[0m"
    
    # Lane colors for variety
    LANE_COLORS = ["\033[31m", "\033[32m", "\033[34m", "\033[35m", "\033[36m"]
    
    max_col = max((n.column for n in nodes), default=0)
    
    for node in nodes:
        line = ""
        for c in range(max_col + 1):
            if c == node.column:
                line += f"{LANE_COLORS[c % len(LANE_COLORS)]}●{C_RESET} "
            else:
                # For now, simplistic: vertical line if lane is active
                # Full rendering requires tracking active edges between nodes
                line += "│ "
                
        # Decorations
        decs = []
        if node.branches:
            decs.append(f"{C_BRANCH}({', '.join(node.branches)}){C_RESET}")
        if node.tags:
            decs.append(f"{C_TAG}tag: {', '.join(node.tags)}{C_RESET}")
            
        dec_str = " ".join(decs)
        if dec_str:
            dec_str = f" {dec_str}"
            
        print(f"{line}{C_SHA}{node.sha[:7]}{C_RESET}{dec_str} {node.message}")
