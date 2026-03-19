"""
deep.core.graph
~~~~~~~~~~~~~~~~~~~~
Core graph traversal and rendering for history visualization.
"""

from __future__ import annotations
import heapq
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any
from dataclasses import dataclass, field

# Defer these to avoid circular imports if needed, 
# but they are currently used in get_history_graph.
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

def get_history_graph(dg_dir: Path, start_sha: Optional[str] = None, max_count: Optional[int] = 100, all_refs: bool = False) -> List[GraphNode]:
    """Traverse commits and build a graph structure for rendering."""
    if max_count is not None and not isinstance(max_count, int):
        from deep.core.errors import DeepCLIException
        raise DeepCLIException(1)
    
    from deep.storage.commit_graph import DeepHistoryGraph
    
    objects_dir = dg_dir / "objects"
    cg = DeepHistoryGraph(dg_dir)
    use_index = cg.load()
    
    # Identify entry points
    heads: Dict[str, str] = {}
    if all_refs:
        for b in list_branches(dg_dir):
            sha = get_branch(dg_dir, b)
            if sha:
                heads[b] = sha
    elif start_sha:
        heads["HEAD"] = start_sha
    else:
        head_sha = resolve_head(dg_dir)
        if head_sha:
            heads["HEAD"] = head_sha

    tags_map: Dict[str, str] = {}
    for t in list_tags(dg_dir):
        sha = get_tag(dg_dir, t)
        if sha:
            tags_map[t] = sha

    # Priority Queue: (-timestamp, sha) to get newest first
    pq: List[Tuple[int, str]] = []
    processed: Set[str] = set()

    def _get_commit_meta(sha: str) -> Optional[Tuple[int, List[str], str, str]]:
        """Helpers to get essential commit data, using index if possible."""
        if use_index:
            idx = cg.get_commit_index(sha)
            if idx is not None:
                info = cg.get_commit_info(idx)
                if info:
                    tree_sha, p_indices, gen, ts = info
                    parents = [cg._oids[pi].hex() for pi in p_indices]
                    # We still need the message for GraphNode, which isn't in the index yet.
                    # Deep's commit-graph doesn't store messages either, but we could add it.
                    # For now, we load the object for the message.
                    try:
                        commit = read_object(objects_dir, sha)
                        return ts, parents, tree_sha, commit.message.split("\n")[0]
                    except Exception:
                        return ts, parents, tree_sha, ""
        
        try:
            commit = read_object(objects_dir, sha)
            if isinstance(commit, Commit):
                return commit.timestamp, commit.parent_shas, commit.tree_sha, commit.message.split("\n")[0]
        except Exception:
            pass
        return None

    def _push_commit(sha: str):
        if sha in processed: return
        meta = _get_commit_meta(sha)
        if meta:
            ts, parents, tree, msg = meta
            heapq.heappush(pq, (-ts, sha))

    for sha in set(heads.values()):
        _push_commit(sha)
    
    nodes: Dict[str, GraphNode] = {}
    while pq and (max_count is None or len(nodes) < max_count):
        neg_ts, sha = heapq.heappop(pq)
        if sha in processed:
            continue
        processed.add(sha)
        
        meta = _get_commit_meta(sha)
        if not meta:
            continue
            
        ts, parents, tree_sha, msg = meta
        
        # We need a dummy Commit object for GraphNode compatibility if we use index
        # or we refactor GraphNode to not require a full Commit.
        # Let's create a lightweight Commit wrapper or just load it if we must.
        # To avoid breaking types, we'll load the commit object.
        # Optimization: the _get_commit_meta already loaded it for the message.
        try:
            commit = read_object(objects_dir, sha)
            node = GraphNode(
                sha=sha,
                commit=commit,
                parents=parents,
                message=msg
            )
            
            # Decorations
            for b, bsha in heads.items():
                if bsha == sha:
                    node.branches.append(b)
            for t, tsha in tags_map.items():
                if tsha == sha:
                    node.tags.append(t)
            
            nodes[sha] = node
            
            # Push parents
            for p_sha in parents:
                _push_commit(p_sha)
                
        except Exception:
            continue

    return list(nodes.values())


def render_graph(nodes: List[GraphNode]) -> None:
    """Render a list of GraphNodes as a Unicode topology graph."""
    try:
        from deep.utils.ux import Color
    except ImportError:
        class Color:
            CYAN = GREEN = YELLOW = BOLD = DIM = ""
            @staticmethod
            def wrap(c, text): return text

    for i, node in enumerate(nodes):
        decorations = []
        heads = [b for b in node.branches if b == "HEAD"]
        others = [b for b in node.branches if b != "HEAD"]
        
        if heads and others:
            decorations.append(Color.wrap(Color.CYAN, f"HEAD -> {others[0]}"))
            for o in others[1:]:
                decorations.append(Color.wrap(Color.GREEN, o))
        elif heads:
            decorations.append(Color.wrap(Color.CYAN, "HEAD"))
        else:
            for o in others:
                decorations.append(Color.wrap(Color.GREEN, o))
                
        if node.tags:
            for t in node.tags:
                decorations.append(Color.wrap(Color.YELLOW, f"tag: {t}"))
        
        dec_str = ""
        if decorations:
            paren_start = Color.wrap(Color.YELLOW, "(")
            paren_end = Color.wrap(Color.YELLOW, ")")
            dec_str = f" {paren_start}{', '.join(decorations)}{paren_end}"
            
        msg_title = node.message.split("\n")[0] if node.message else ""
        sha_str = Color.wrap(Color.YELLOW, node.sha[:7])
        
        print(f"● {sha_str}{dec_str} {msg_title}")
        
        author_str = node.commit.author if hasattr(node.commit, 'author') else "Unknown"
        print(f"│ {Color.wrap(Color.BOLD, 'Author:')} {Color.wrap(Color.CYAN, author_str)}")
        
        if node.parents and len(node.parents) > 1:
            for p in node.parents[1:]:
                # Merge commit visualization
                print(f"├─ {Color.wrap(Color.DIM, 'Merge: ' + p[:7])}")
                
        if i < len(nodes) - 1:
            print("│")

