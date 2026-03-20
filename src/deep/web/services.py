"""
deep.web.services
~~~~~~~~~~~~~~~~~~~~~
Enterprise-grade Service layer for the Deep Web Dashboard (Pinnacle Upgrade).
"""

from __future__ import annotations
import os
import json
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable

from deep.core.constants import DEEP_DIR
from deep.core.refs import resolve_head, get_current_branch, list_branches, resolve_revision
from deep.core.repository import find_repo
from deep.storage.index import read_index
from deep.core.status import compute_status
from deep.core.errors import DeepError
from deep.core.pr import PRManager
from deep.core.issue import IssueManager
from deep.core.diff import diff_working_tree, diff_trees

class DashboardService:
    def __init__(self, dg_dir: Path, repo_root: Path):
        self.dg_dir = dg_dir
        self.repo_root = repo_root
        self.pr_manager = PRManager(dg_dir)
        self.issue_manager = IssueManager(dg_dir)

    def _safe(self, fn: Callable, *args, **kwargs) -> Dict[str, Any]:
        """Wrap all operations in a safety net for the UI."""
        try:
            res = fn(*args, **kwargs)
            return {"success": True, "data": res}
        except Exception as e:
            traceback.print_exc()
            return {"success": False, "error": str(e)}

    # --- File System (PINNACLE NESTED TREE) ---

    def get_tree(self) -> Dict[str, Any]:
        """Return a nested dictionary structure of the repository, excluding .git, node_modules, and .deep."""
        return self._safe(self._get_tree_pinnacle)

    def _get_tree_pinnacle(self) -> Dict[str, Any]:
        tree_dict = {}
        exclude = {".git", "node_modules", DEEP_DIR}
        
        for root, dirs, files in os.walk(self.repo_root):
            # Prune excluded directories
            dirs[:] = [d for d in dirs if d not in exclude and not d.startswith(".")]
            
            rel_root = Path(root).relative_to(self.repo_root)
            if str(rel_root) == '.':
                current_level = tree_dict
            else:
                current_level = tree_dict
                for part in rel_root.parts:
                    if part not in current_level:
                        current_level[part] = {"_type": "dir", "children": {}}
                    current_level = current_level[part]["children"]
            
            for d in dirs:
                if d not in current_level:
                    current_level[d] = {"_type": "dir", "children": {}}
            
            for f in files:
                current_level[f] = {
                    "_type": "file", 
                    "path": (rel_root / f).as_posix()
                }
        return {"tree": tree_dict}

    def get_file(self, path: str) -> Dict[str, Any]:
        file_path = self.repo_root / path
        if not file_path.exists():
            return {"success": False, "error": f"File not found: {path}"}
        
        try:
            data = file_path.read_bytes()
            # Detect binary (null byte check)
            is_binary = b'\x00' in data[:8000]
            if is_binary:
                return {"path": path, "content": "[Binary File]", "isBinary": True}
            
            content = data.decode('utf-8', errors='replace')
            return {"path": path, "content": content, "isBinary": False}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def save_file(self, path: str, content: str) -> Dict[str, Any]:
        return self._safe(self._save_file_internal, path, content)

    def _save_file_internal(self, path: str, content: str) -> Dict[str, Any]:
        full_path = self.repo_root / path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content, encoding='utf-8')
        return {"path": path, "size": len(content)}

    # --- Git Operations ---

    def get_full_status(self) -> Dict[str, Any]:
        return self._safe(self._get_status_internal)

    def _get_status_internal(self) -> Dict[str, Any]:
        status = compute_status(self.repo_root)
        current_branch = get_current_branch(self.dg_dir) or "DETACHED"
        return {
            "branch": current_branch,
            "staged": status.staged_new + status.staged_modified + status.staged_deleted,
            "modified": status.modified,
            "deleted": status.deleted,
            "untracked": status.untracked,
            "ahead": status.ahead_count,
            "behind": status.behind_count
        }

    def commit(self, message: str, author: str = "Deep Web") -> Dict[str, Any]:
        return self._safe(self._commit_internal, message, author)

    def _commit_internal(self, message: str, author: str) -> Dict[str, Any]:
        from deep.commands.commit_cmd import run
        class Args:
            def __init__(self, m, a):
                self.message = m; self.all = False; self.ai = False; self.sign = False
        run(Args(message, author))
        return {"status": "success", "sha": resolve_head(self.dg_dir)}

    def get_graph(self) -> Dict[str, Any]:
        return self._safe(self._get_graph_internal)

    def _get_graph_internal(self) -> Dict[str, Any]:
        from deep.storage.objects import read_object, Commit
        from deep.core.refs import list_branches, get_branch, list_tags
        
        objects_dir = self.dg_dir / "objects"
        commits = []
        refs = {}
        
        for b in list_branches(self.dg_dir):
            sha = get_branch(self.dg_dir, b)
            if sha: refs[f"branch:{b}"] = sha
        for t in list_tags(self.dg_dir):
            sha = resolve_revision(self.dg_dir, t)
            if sha: refs[f"tag:{t}"] = sha
            
        head = resolve_head(self.dg_dir)
        if head:
            refs["HEAD"] = head
            queue = [head]
            visited = set()
            while queue and len(commits) < 100:
                sha = queue.pop(0)
                if sha in visited: continue
                visited.add(sha)
                try:
                    obj = read_object(objects_dir, sha)
                    if isinstance(obj, Commit):
                        commits.append({
                            "sha": sha,
                            "author": obj.author,
                            "message": obj.message,
                            "parents": obj.parent_shas,
                            "timestamp": obj.timestamp
                        })
                        queue.extend(obj.parent_shas)
                except: continue
        
        return {"commits": commits, "refs": refs}

    def checkout_branch(self, name: str) -> Dict[str, Any]:
        return self._safe(self._checkout_internal, name)

    def _checkout_internal(self, name: str) -> Dict[str, Any]:
        from deep.commands.checkout_cmd import run
        class Args:
            def __init__(self, t): self.target = t; self.force = False; self.branch = False
        run(Args(name))
        return {"status": "success", "branch": name}

    def create_branch(self, name: str, start_point: str = "HEAD") -> Dict[str, Any]:
        return self._safe(self._create_branch_internal, name, start_point)

    def _create_branch_internal(self, name: str, start_point: str) -> Dict[str, Any]:
        from deep.commands.branch_cmd import run
        class Args:
            def __init__(self, n, s): self.name = n; self.start_point = s; self.delete = False
        run(Args(name, start_point))
        return {"status": "success", "branch": name}

    def merge_branch(self, branch: str) -> Dict[str, Any]:
        return self._safe(self._merge_internal, branch)

    def _merge_internal(self, branch: str) -> Dict[str, Any]:
        from deep.commands.merge_cmd import run
        class Args:
            def __init__(self, b): self.branch = b
        run(Args(branch))
        return {"status": "success", "message": f"Merged {branch}"}

    # --- Diff Engine ---

    def get_diff(self) -> Dict[str, Any]:
        return self._safe(self._get_diff_internal)

    def _get_diff_internal(self) -> Dict[str, Any]:
        unstaged_diffs = diff_working_tree(self.repo_root)
        full_diff = ""
        for path, text in unstaged_diffs:
            full_diff += text + "\n"
        return {"diff": full_diff}

    # --- PR & Issues (Local PINNACLE Upgrade) ---

    def get_prs_local(self) -> Dict[str, Any]:
        return self._safe(self._get_prs_local_internal)

    def _get_prs_local_internal(self) -> Dict[str, Any]:
        prs = self.pr_manager.list_prs()
        return {"prs": [self._serialize_pr(p) for p in prs]}

    def _serialize_pr(self, pr: Any) -> Dict[str, Any]:
        from dataclasses import asdict
        return asdict(pr)

    def get_issues_local(self) -> Dict[str, Any]:
        return self._safe(self._get_issues_local_internal)

    def _get_issues_local_internal(self) -> Dict[str, Any]:
        issues = self.issue_manager.list_issues()
        return {"issues": [self._serialize_issue(i) for i in issues]}

    def _serialize_issue(self, issue: Any) -> Dict[str, Any]:
        from dataclasses import asdict
        return asdict(issue)

    def create_pr(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return self._safe(self._create_pr_internal, data)

    def _create_pr_internal(self, data: Dict[str, Any]) -> Dict[str, Any]:
        pr = self.pr_manager.create_pr(
            title=data.get("title", "Untitled PR"),
            author=data.get("author", "Deep Studio"),
            head=data.get("head", ""),
            base=data.get("base", "main"),
            body=data.get("body", "")
        )
        return {"status": "success", "id": pr.id}

    def review_pr(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return self._safe(self._review_pr_internal, data)

    def _review_pr_internal(self, data: Dict[str, Any]) -> Dict[str, Any]:
        pr_id = int(data.get("pr_id"))
        state = data.get("state", "commented")
        comment = data.get("comment", "")
        author = data.get("author", "Deep Studio")
        self.pr_manager.add_review(pr_id, author, state, comment)
        return {"status": "success"}

    def merge_local_pr(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return self._safe(self._merge_local_pr_internal, data)

    def _merge_local_pr_internal(self, data: Dict[str, Any]) -> Dict[str, Any]:
        pr_id = int(data.get("pr_id"))
        self.pr_manager.merge_pr(pr_id)
        return {"status": "success"}

    def create_issue(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return self._safe(self._create_issue_internal, data)

    def _create_issue_internal(self, data: Dict[str, Any]) -> Dict[str, Any]:
        issue = self.issue_manager.create_issue(
            title=data.get("title", "Untitled Issue"),
            description=data.get("body", ""),
            type=data.get("type", "task"),
            author=data.get("author", "Deep Studio")
        )
        return {"status": "success", "id": issue.id}
