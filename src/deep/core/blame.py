"""
deep.core.blame
~~~~~~~~~~~~~~~~~~~
Line-level attribution (blame) engine.

Calculates which commit and author last modified each line of a file 
by traversing history and analyzing diffs.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from deep.storage.objects import read_object, Commit, Blob
from deep.core.refs import resolve_head
from deep.core.diff import diff_lines


@dataclass
class BlameHunk:
    commit_sha: str
    author: str
    timestamp: float
    start_line: int  # 1-indexed
    num_lines: int


def get_blame(dg_dir: Path, rel_path: str, commit_sha: str = "") -> List[BlameHunk]:
    """Return line-of-origin attribution for a file at a specific commit."""
    if not commit_sha:
        commit_sha = resolve_head(dg_dir)
    if not commit_sha:
        return []

    # 1. Get the current content of the file at commit_sha
    try:
        commit = read_object(dg_dir / "objects", commit_sha)
        if not isinstance(commit, Commit):
            return []
        
        from deep.web.dashboard import _tree_entries_flat
        entries = _tree_entries_flat(dg_dir / "objects", commit.tree_sha)
        blob_sha = entries.get(rel_path)
        if not blob_sha:
            return []
            
        obj = read_object(dg_dir / "objects", blob_sha)
        if not isinstance(obj, Blob):
            return []
        
        lines = obj.data.decode("utf-8", errors="replace").splitlines()
    except Exception:
        return []

    # Initialize attribution: all lines attributed to current commit
    # (We will push attribution back as we find older versions)
    attribution = [commit_sha] * len(lines)
    
    # 2. Traverse back in history
    # For a simple implementation, we'll just check common parents
    # and see if the line existed there.
    # In a full implementation, we'd use a more robust "moving lines" algorithm.
    
    # Simplified approach: for each line, find the earliest commit where 
    # the file content was the same at that line.
    
    queue = [(commit_sha, lines)]
    visited = {commit_sha}
    
    while queue:
        curr_sha, curr_lines = queue.pop(0)
        curr_commit = read_object(dg_dir / "objects", curr_sha)
        
        for p_sha in curr_commit.parent_shas:
            if p_sha in visited:
                continue
            visited.add(p_sha)
            
            p_commit = read_object(dg_dir / "objects", p_sha)
            p_entries = _tree_entries_flat(dg_dir / "objects", p_commit.tree_sha)
            p_blob_sha = p_entries.get(rel_path)
            
            if not p_blob_sha:
                continue # File didn't exist in parent
                
            p_obj = read_object(dg_dir / "objects", p_blob_sha)
            p_lines = p_obj.data.decode("utf-8", errors="replace").splitlines()
            
            # Simple line-by-line comparison
            # If line i in curr_lines is the same as line j in p_lines, 
            # we *could* attribute it to p_sha or older.
            # But we need to maintain indices. 
            # We'll use a very basic heuristic: if lines are identical, p_sha is the new owner.
            
            import difflib
            s = difflib.SequenceMatcher(None, p_lines, curr_lines)
            for tag, i1, i2, j1, j2 in s.get_opcodes():
                if tag == 'equal':
                    # Lines j1:j2 in curr_lines are the same as i1:i2 in p_lines
                    # Any line in j1:j2 currently attributed to curr_sha 
                    # can be pushed back to p_sha.
                    for idx in range(j1, j2):
                        if attribution[idx] == curr_sha:
                            attribution[idx] = p_sha
            
            queue.append((p_sha, p_lines))

    # 3. Group into hunks
    hunks = []
    if not attribution:
        return []
        
    curr_sha = attribution[0]
    start = 1
    for i, sha in enumerate(attribution):
        if sha != curr_sha:
            # Commit info for previous hunk
            c = read_object(dg_dir / "objects", curr_sha)
            hunks.append(BlameHunk(curr_sha, c.author, c.timestamp, start, i + 1 - start))
            curr_sha = sha
            start = i + 1
            
    # Final hunk
    c = read_object(dg_dir / "objects", curr_sha)
    hunks.append(BlameHunk(curr_sha, c.author, c.timestamp, start, len(attribution) + 1 - start))
    
    return hunks


def semantic_blame(dg_dir: Path, rel_path: str, commit_sha: str = "") -> dict[str, str]:
    """Map function/class names to their last modifying commit author."""
    hunks = get_blame(dg_dir, rel_path, commit_sha)
    if not hunks:
        return {}
        
    # Get file content to find boundaries
    from deep.storage.objects import read_object, Commit, Blob
    if not commit_sha:
        from deep.core.refs import resolve_head
        commit_sha = resolve_head(dg_dir)
    
    commit = read_object(dg_dir / "objects", commit_sha)
    from deep.web.dashboard import _tree_entries_flat
    entries = _tree_entries_flat(dg_dir / "objects", commit.tree_sha)
    blob_sha = entries.get(rel_path)
    if not blob_sha: return {}
    
    obj = read_object(dg_dir / "objects", blob_sha)
    lines = obj.data.decode("utf-8", errors="replace").splitlines()
    
    import re
    # Simple Python/JS boundary detection
    pattern = re.compile(r"^(def |class |async def |function )([\w\d_]+)")
    
    symbol_authors = {}
    current_symbol = None
    
    # Map line number to author
    line_authors = {}
    for h in hunks:
        for i in range(h.start_line, h.start_line + h.num_lines):
            line_authors[i] = h.author

    for i, line in enumerate(lines, 1):
        match = pattern.match(line.strip())
        if match:
            current_symbol = match.group(2)
        
        if current_symbol:
            # Attribution for the symbol
            symbol_authors[current_symbol] = line_authors.get(i, "unknown")
            
    return symbol_authors
