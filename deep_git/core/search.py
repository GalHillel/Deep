"""
deep_git.core.search
~~~~~~~~~~~~~~~~~~~~
Historical search engine for DeepGit.

Searches for patterns across all commits and their trees.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Set

from deep_git.core.objects import read_object, Commit, Blob
from deep_git.core.refs import log_history


@dataclass
class SearchResult:
    commit_sha: str
    rel_path: str
    line_num: int
    content: str


def search_history(dg_dir: Path, pattern: str, max_results: int = 100) -> List[SearchResult]:
    """Search for the given pattern in all commits' trees."""
    regex = re.compile(pattern, re.IGNORECASE)
    results: List[SearchResult] = []
    
    shas = log_history(dg_dir)
    objects_dir = dg_dir / "objects"
    
    # Cache to avoid re-searching identical blobs
    searched_blobs: dict[str, List[tuple[int, str]]] = {}
    
    from deep_git.web.dashboard import _tree_entries_flat
    
    for sha in shas:
        if len(results) >= max_results:
            break
            
        commit = read_object(objects_dir, sha)
        if not isinstance(commit, Commit):
            continue
            
        entries = _tree_entries_flat(objects_dir, commit.tree_sha)
        for rel_path, blob_sha in entries.items():
            if len(results) >= max_results:
                break
                
            if blob_sha not in searched_blobs:
                blob_matches = []
                try:
                    obj = read_object(objects_dir, blob_sha)
                    if isinstance(obj, Blob):
                        text = obj.data.decode("utf-8", errors="replace")
                        for i, line in enumerate(text.splitlines(), 1):
                            if regex.search(line):
                                blob_matches.append((i, line))
                except Exception:
                    pass
                searched_blobs[blob_sha] = blob_matches
            
            for line_num, content in searched_blobs[blob_sha]:
                results.append(SearchResult(sha, rel_path, line_num, content.strip()))
                if len(results) >= max_results:
                    break
                    
    return results
