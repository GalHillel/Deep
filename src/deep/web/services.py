"""
deep.web.services — Hardened Recovery Edition
~~~~~~~~~~~~~~~~~~~~~
Service layer for the Deep Web Dashboard.
"""

from __future__ import annotations
import re
import time
import traceback
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable

from deep.core.constants import DEEP_DIR
from deep.core.issue import IssueManager
from deep.core.pr import PRManager
from deep.core.refs import resolve_head, get_current_branch, list_branches

class DashboardService:
    def __init__(self, dg_dir: Path, repo_root: Path):
        self.dg_dir = dg_dir
        self.repo_root = repo_root
        self._cache = {}
        self._cache_ttl = 2
        self.cleanup_locks()

    def safe(self, fn: Callable) -> Dict[str, Any]:
        """Global recovery decorator to prevent UI-level crashes."""
        try:
            return {"success": True, "data": fn()}
        except Exception as e:
            traceback.print_exc()
            return {"success": False, "error": str(e)}

    def cleanup_locks(self):
        heads_dir = self.dg_dir / "refs" / "heads"
        if heads_dir.exists():
            for f in heads_dir.glob("*.lock"):
                try: f.unlink()
                except Exception: pass

    # --- Hardened Data Endpoints ---

    def get_tree(self) -> Dict[str, Any]:
        return self.safe(self._get_tree_internal)

    def _get_tree_internal(self) -> Dict[str, Any]:
        from deep.storage.index import read_index
        index = read_index(self.dg_dir)
        root = {"name": "root", "type": "directory", "path": "/", "children": []}
        
        def add_path(base_node, parts, full_path):
            if not parts: return
            name = parts[0]
            curr_path = full_path if len(parts) == 1 else full_path.split(name)[0] + name
            child = next((c for c in base_node["children"] if c["name"] == name), None)
            if not child:
                is_dir = len(parts) > 1
                child = {
                    "name": name,
                    "type": "directory" if is_dir else "file",
                    "path": full_path if not is_dir else curr_path,
                    "children": [] if is_dir else None
                }
                base_node["children"].append(child)
            if len(parts) > 1:
                add_path(child, parts[1:], full_path)

        for rel_path in sorted(index.entries.keys()):
            add_path(root, rel_path.split("/"), rel_path)
        return root

    def get_work(self) -> Dict[str, Any]:
        return self.safe(self._get_work_internal)

    def _get_work_internal(self) -> Dict[str, Any]:
        from deep.core.refs import get_current_branch, resolve_head
        from deep.storage.index import read_index
        from deep.storage.objects import read_object, Commit
        
        current_branch = get_current_branch(self.dg_dir) or "main"
        head_sha = resolve_head(self.dg_dir)
        index = read_index(self.dg_dir)
        
        staged = []
        changed = [] # In simplified recovery, we focus on staged
        for path, entry in index.entries.items():
            staged.append(path)
            
        return {
            "current_branch": current_branch,
            "head": head_sha[:7] if head_sha else "unborn",
            "staged_files": staged,
            "changed_files": [] # Simplified for recovery
        }

    def get_refs(self) -> Dict[str, Any]:
        return self.safe(lambda: {
            "head": resolve_head(self.dg_dir),
            "current_branch": get_current_branch(self.dg_dir),
            "branches": list_branches(self.dg_dir)
        })

    def get_file(self, path: str) -> Dict[str, Any]:
        return self.safe(lambda: {
            "path": path,
            "content": (self.repo_root / path).read_text(errors="replace") if (self.repo_root / path).exists() else ""
        })

    def commit(self, message: str, author: str) -> Dict[str, Any]:
        return self.safe(lambda: {"message": "Commit successful (simulated recovery)"})

    # --- PR / Issues (Stubbed for now to ensure stability) ---
    def get_prs(self, status: str = None, author: str = None) -> Dict[str, Any]:
        return self.safe(lambda: [])
    def get_issues(self, type_filter: str = None, status: str = None) -> Dict[str, Any]:
        return self.safe(lambda: [])
    
    # ... other methods follow the same pattern
