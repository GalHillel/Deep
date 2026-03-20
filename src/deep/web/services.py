"""
deep.web.services
~~~~~~~~~~~~~~~~~~~~~
Service layer for the Deep Web Dashboard.

All API handlers delegate to DashboardService — no direct file/manager
access in the HTTP handler.  Provides in-memory caching (2 s TTL),
immediate cache invalidation on mutations, a lightweight permission
layer, and an activity log.
"""

from __future__ import annotations

import time
import traceback
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from deep.core.constants import DEEP_DIR  # type: ignore[import]
from deep.core.issue import IssueManager  # type: ignore[import]
from deep.core.pr import PRManager  # type: ignore[import]
from deep.core.refs import resolve_head, get_current_branch  # type: ignore[import]


class DashboardService:
    """Central service for all dashboard data operations."""

    def __init__(self, dg_dir: Path, repo_root: Path):
        self.dg_dir = dg_dir
        self.repo_root = repo_root
        self._cache: Dict[str, tuple] = {}  # key → (data, timestamp)
        self._cache_ttl = 2  # seconds
        self._activity: List[Dict[str, Any]] = []  # last 50 events
        self._max_activity = 50
        self.cleanup_locks()

    def cleanup_locks(self):
        """Standard maintenance: delete stale .lock files in refs/heads/ on startup."""
        heads_dir = self.dg_dir / "refs" / "heads"
        if heads_dir.exists():
            for f in heads_dir.glob("*.lock"):
                try:
                    f.unlink()
                except Exception:
                    pass

    # ── Cache helpers ────────────────────────────────────────────────

    def _cache_get(self, key: str) -> Any:
        if key in self._cache:
            data, ts = self._cache[key]
            if time.time() - ts < self._cache_ttl:
                return data
        return None

    def _cache_set(self, key: str, data: Any) -> None:
        self._cache[key] = (data, time.time())

    def _invalidate(self, *keys: str) -> None:
        for k in keys:
            self._cache.pop(k, None)

    # ── Activity log ─────────────────────────────────────────────────

    def _log_activity(self, event_type: str, message: str, **extra: Any) -> None:
        entry = {
            "type": event_type,
            "message": message,
            "timestamp": time.time(),
            **extra,
        }
        self._activity.insert(0, entry)
        self._activity = self._activity[: self._max_activity]

    def get_activity(self) -> List[Dict[str, Any]]:
        return list(self._activity)

    # ── Health ───────────────────────────────────────────────────────

    def get_health(self) -> Dict[str, Any]:
        try:
            prm = PRManager(self.dg_dir)
            im = IssueManager(self.dg_dir)
            return {
                "status": "ok",
                "repo": str(self.repo_root),
                "prs": len(prm.list_prs()),
                "issues": len(im.list_issues()),
            }
        except Exception as exc:
            return {"status": "degraded", "error": str(exc)}

    # ── PRs ──────────────────────────────────────────────────────────

    def get_prs(
        self,
        status: Optional[str] = None,
        author: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        cache_key = f"prs:{status or ''}:{author or ''}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        try:
            prm = PRManager(self.dg_dir)
            prs = prm.list_prs()
        except Exception:
            return []

        result: List[Dict[str, Any]] = []
        for pr in prs:
            if status and pr.status != status:
                continue
            if author and pr.author != author.lower():
                continue

            approvals = sum(
                1 for r in pr.reviews.values() if r.get("status") == "approved"
            )
            changes_requested = sum(
                1 for r in pr.reviews.values() if r.get("status") == "changes_requested"
            )
            unresolved = pr.unresolved_count
            merge_ready = (
                pr.status == "open"
                and approvals >= pr.approvals_required
                and changes_requested == 0
                and unresolved == 0
            )

            result.append({
                "id": pr.id,
                "title": pr.title,
                "head": pr.head,
                "base": pr.base,
                "status": pr.status,
                "author": pr.author,
                "approvals": approvals,
                "required": pr.approvals_required,
                "changes_requested": changes_requested,
                "unresolved_threads": unresolved,
                "merge_ready": merge_ready,
                "linked_issue": pr.linked_issue,
                "created_at": pr.created_at,
                "updated_at": pr.updated_at,
            })

        self._cache_set(cache_key, result)
        return result

    # ── PR detail ────────────────────────────────────────────────────

    def get_pr_detail(self, pr_id: int) -> Optional[Dict[str, Any]]:
        """Full detail — NOT cached (on-demand)."""
        try:
            prm = PRManager(self.dg_dir)
            pr = prm.get_pr(pr_id)
        except Exception:
            return None
        if pr is None:
            return None

        approvals = sum(
            1 for r in pr.reviews.values() if r.get("status") == "approved"
        )
        changes_requested = sum(
            1 for r in pr.reviews.values() if r.get("status") == "changes_requested"
        )
        unresolved = pr.unresolved_count
        merge_ready = (
            pr.status == "open"
            and approvals >= pr.approvals_required
            and changes_requested == 0
            and unresolved == 0
        )

        threads_data = []
        for t in pr.threads:
            replies = [{"author": r.author, "text": r.text, "created_at": r.created_at} for r in t.replies]
            threads_data.append({
                "id": t.id,
                "author": t.author,
                "text": t.text,
                "created_at": t.created_at,
                "resolved": t.resolved,
                "replies": replies,
            })

        return {
            "id": pr.id,
            "title": pr.title,
            "head": pr.head,
            "base": pr.base,
            "status": pr.status,
            "body": pr.body,
            "author": pr.author,
            "reviews": pr.reviews,
            "threads": threads_data,
            "commits": pr.commits,
            "approvals": approvals,
            "required": pr.approvals_required,
            "changes_requested": changes_requested,
            "unresolved_threads": unresolved,
            "merge_ready": merge_ready,
            "linked_issue": pr.linked_issue,
            "requested_reviewers": pr.requested_reviewers,
            "created_at": pr.created_at,
            "updated_at": pr.updated_at,
        }

    # ── Issues ───────────────────────────────────────────────────────

    def get_issues(
        self,
        type_filter: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        cache_key = f"issues:{type_filter or ''}:{status or ''}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        try:
            im = IssueManager(self.dg_dir)
            issues = im.list_issues()
        except Exception:
            return []

        result: List[Dict[str, Any]] = []
        for iss in issues:
            if type_filter and iss.type != type_filter:
                continue
            if status and iss.status != status:
                continue
            result.append({
                "id": iss.id,
                "title": iss.title,
                "description": iss.description,
                "type": iss.type,
                "status": iss.status,
                "author": iss.author,
                "labels": iss.labels,
                "assignee": iss.assignee,
                "linked_prs": iss.linked_prs,
                "timeline": iss.timeline,
                "created_at": iss.created_at,
            })

        self._cache_set(cache_key, result)
        return result

    # ── Work snapshot ────────────────────────────────────────────────

    def get_work(self) -> Dict[str, Any]:
        cached = self._cache_get("work")
        if cached is not None:
            return cached

        current_branch = ""
        try:
            current_branch = get_current_branch(self.dg_dir) or ""
        except Exception:
            pass

        prs = self.get_prs()
        issues = self.get_issues()

        open_prs = [p for p in prs if p["status"] == "open"]
        open_issues = [iss for iss in issues if iss["status"] == "open"]

        # Find active PR for current branch
        active_pr = None
        for p in open_prs:
            if p["head"] == current_branch:
                active_pr = p
                break

        # Find related issue
        related_issue = None
        if active_pr and active_pr.get("linked_issue"):
            for iss in issues:
                if iss["id"] == active_pr["linked_issue"]:
                    related_issue = iss
                    break

        result = {
            "current_branch": current_branch,
            "open_prs": len(open_prs),
            "open_issues": len(open_issues),
            "active_pr": active_pr,
            "related_issue": related_issue,
        }
        self._cache_set("work", result)
        return result

    # ── POST Actions ─────────────────────────────────────────────────

    def _check_permission(
        self, pr_id: int, author: str, action: str
    ) -> Optional[str]:
        """Return error message if not permitted, else None."""
        try:
            prm = PRManager(self.dg_dir)
            pr = prm.get_pr(pr_id)
        except Exception as exc:
            return str(exc)
        if pr is None:
            return f"PR #{pr_id} not found"

        author = author.lower()

        if action == "approve":
            if author == pr.author:
                return "Cannot approve your own PR"
            if pr.requested_reviewers and author not in pr.requested_reviewers:
                return f"'{author}' is not an assigned reviewer"

        if action == "request_changes":
            if author == pr.author:
                return "Cannot request changes on your own PR"
            if pr.requested_reviewers and author not in pr.requested_reviewers:
                return f"'{author}' is not an assigned reviewer"

        if action == "merge":
            # Allow author or any reviewer who approved
            is_author = author == pr.author
            is_reviewer = author in pr.reviews and pr.reviews[author].get("status") == "approved"
            if not is_author and not is_reviewer:
                return "Only PR author or an approving reviewer can merge"

        return None

    def approve_pr(self, pr_id: int, author: str) -> Dict[str, Any]:
        perm_err = self._check_permission(pr_id, author, "approve")
        if perm_err:
            return {"error": perm_err}

        try:
            prm = PRManager(self.dg_dir)
            prm.add_review(pr_id, author, "approved")
            self._invalidate_pr_caches()
            self._log_activity("review_added", f"{author} approved PR #{pr_id}", pr_id=pr_id)
            return {"message": f"PR #{pr_id} approved by {author}"}
        except Exception as exc:
            return {"error": str(exc)}

    def request_changes_pr(self, pr_id: int, author: str, comment: str = "") -> Dict[str, Any]:
        perm_err = self._check_permission(pr_id, author, "request_changes")
        if perm_err:
            return {"error": perm_err}

        try:
            prm = PRManager(self.dg_dir)
            prm.add_review(pr_id, author, "changes_requested", comment)
            self._invalidate_pr_caches()
            self._log_activity("changes_requested", f"{author} requested changes on PR #{pr_id}", pr_id=pr_id)
            return {"message": f"Changes requested on PR #{pr_id} by {author}"}
        except Exception as exc:
            return {"error": str(exc)}

    def resolve_thread_pr(self, pr_id: int, thread_id: int) -> Dict[str, Any]:
        try:
            prm = PRManager(self.dg_dir)
            prm.resolve_thread(pr_id, thread_id)
            self._invalidate_pr_caches()
            self._log_activity("thread_resolved", f"Thread #{thread_id} resolved in PR #{pr_id}", pr_id=pr_id)
            return {"message": f"Thread #{thread_id} resolved in PR #{pr_id}"}
        except Exception as exc:
            return {"error": str(exc)}

    def merge_pr(self, pr_id: int, author: str = "") -> Dict[str, Any]:
        if author:
            perm_err = self._check_permission(pr_id, author, "merge")
            if perm_err:
                return {"error": perm_err}

        try:
            prm = PRManager(self.dg_dir)
            pr = prm.get_pr(pr_id)
            if not pr:
                return {"error": f"PR #{pr_id} not found"}

            # Check merge readiness
            approvals = sum(1 for r in pr.reviews.values() if r.get("status") == "approved")
            changes_requested = sum(1 for r in pr.reviews.values() if r.get("status") == "changes_requested")
            if approvals < pr.approvals_required:
                return {"error": f"Not enough approvals ({approvals}/{pr.approvals_required})"}
            if changes_requested > 0:
                return {"error": "Unresolved change requests"}
            if pr.unresolved_count > 0:
                return {"error": f"{pr.unresolved_count} unresolved thread(s)"}

            prm.merge_pr(pr_id)
            self._invalidate_pr_caches()
            self._log_activity("merge_completed", f"PR #{pr_id} merged: {pr.title}", pr_id=pr_id)
            return {"message": f"PR #{pr_id} merged successfully"}
        except Exception as exc:
            return {"error": str(exc)}

    # ── Workspace / Web IDE ──────────────────────────────────────────

    def _resolve_safe_path(self, rel_path: str) -> Path:
        full_path = (self.repo_root / rel_path).resolve()
        if not str(full_path).startswith(str(self.repo_root.resolve())):
            raise ValueError(f"Invalid path: {rel_path}")
        return full_path

    def get_tree(self) -> Dict[str, Any]:
        cache_key = "tree"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        import os
        
        def build_node(dir_path: str, name: str) -> Dict[str, Any]:
            node = {"name": name, "type": "folder", "children": [], "path": dir_path}
            try:
                entries = sorted(os.listdir(self.repo_root / dir_path) if dir_path else os.listdir(self.repo_root))
            except Exception:
                return node
                
            for entry in entries:
                if entry.startswith('.') or entry in ('node_modules', '__pycache__'):
                    continue
                rel_path = os.path.join(dir_path, entry).replace('\\', '/') if dir_path else entry
                full_path = self.repo_root / rel_path
                
                if full_path.is_dir():
                    node["children"].append(build_node(rel_path, entry))
                elif full_path.is_file():
                    node["children"].append({"name": entry, "type": "file", "path": rel_path})
            
            # Sort folders first, then files
            node["children"].sort(key=lambda x: (0 if x["type"] == "folder" else 1, x["name"]))
            return node

        tree = build_node("", "root")
        self._cache_set(cache_key, tree)
        return tree

    def _is_probably_binary(self, data: bytes) -> bool:
        if not data:
            return False
        # Allow UTF-16 BOM
        if data.startswith((b'\xff\xfe', b'\xfe\xff')):
            return False
        # Heuristic: too many null bytes = binary
        null_ratio = data[:1024].count(b'\x00') / max(1, len(data[:1024]))
        return null_ratio > 0.3

    def _decode_file(self, raw_bytes: bytes) -> str:
        # UTF-16 (Windows PowerShell)
        if raw_bytes.startswith((b'\xff\xfe', b'\xfe\xff')):
            try:
                return raw_bytes.decode('utf-16')
            except Exception:
                pass
        # UTF-8
        try:
            return raw_bytes.decode('utf-8')
        except Exception:
            return raw_bytes.decode('utf-8', errors='replace')

    def get_file(self, rel_path: str) -> Dict[str, Any]:
        """Robust file reader with encoding and binary detection."""
        MAX_FILE_SIZE = 2 * 1024 * 1024  # 2MB
        try:
            file_path = self._resolve_safe_path(rel_path)
            
            # New file handling
            if not file_path.exists():
                return {
                    "content": "",
                    "path": rel_path,
                    "is_new": True,
                    "is_binary": False
                }
                
            if not file_path.is_file():
                return {"error": f"Path is not a file: {rel_path}"}
            
            size = file_path.stat().st_size
            if size > MAX_FILE_SIZE:
                return {
                    "is_binary": True,
                    "content": f"File too large ({size//1024} KB)",
                    "path": rel_path
                }

            with open(file_path, 'rb') as f:
                raw = f.read()

            if self._is_probably_binary(raw):
                return {
                    "is_binary": True,
                    "content": "Binary file cannot be displayed",
                    "path": rel_path
                }

            content = self._decode_file(raw)
            return {
                "content": content,
                "path": rel_path,
                "size": size,
                "is_binary": False,
                "is_new": False
            }
        except Exception as e:
            return {"error": str(e)}

    def save_and_commit(self, rel_path: str, content: str, message: str, author: str) -> Dict[str, Any]:
        """Robust save and commit using internal command runners."""
        import argparse
        try:
            file_path = self._resolve_safe_path(rel_path)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Save file
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content or "")

            # Deep Add
            from deep.commands.add_cmd import run as run_add
            run_add(argparse.Namespace(paths=[rel_path], dg_dir=self.dg_dir, repo_root=self.repo_root))

            # Deep Commit
            from deep.commands.commit_cmd import run as run_commit
            run_commit(argparse.Namespace(
                message=message, 
                ai=False, 
                allow_empty=False, 
                dg_dir=self.dg_dir, 
                repo_root=self.repo_root,
                patch=False
            ))

            self._invalidate("tree", "work")
            self._log_activity("commit_created", f"{author} committed changes to {rel_path}")
            return {"message": "Changes committed successfully"}
        except Exception as e:
            return {"error": str(e)}

    def create_file(self, rel_path: str, author: str) -> Dict[str, Any]:
        try:
            file_path = self._resolve_safe_path(rel_path)
            if file_path.exists():
                return {"error": "File already exists"}
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text("", encoding="utf-8")
            self._invalidate("tree")
            return {"message": "File created"}
        except Exception as e:
            return {"error": str(e)}

    def delete_file(self, rel_path: str, author: str) -> Dict[str, Any]:
        try:
            file_path = self._resolve_safe_path(rel_path)
            if not file_path.exists():
                return {"error": "File not found"}
            if file_path.is_dir():
                import shutil
                shutil.rmtree(file_path)
            else:
                file_path.unlink()
            self._invalidate("tree")
            return {"message": "File deleted"}
        except Exception as e:
            return {"error": str(e)}

    def rename_file(self, old_path: str, new_path: str, author: str) -> Dict[str, Any]:
        try:
            old_file = self._resolve_safe_path(old_path)
            new_file = self._resolve_safe_path(new_path)
            if not old_file.exists():
                return {"error": "Source file not found"}
            if new_file.exists():
                return {"error": "Destination path already exists"}
            new_file.parent.mkdir(parents=True, exist_ok=True)
            old_file.rename(new_file)
            self._invalidate("tree")
            return {"message": "File renamed"}
        except Exception as e:
            return {"error": str(e)}



    def create_branch(self, name: str, author: str) -> Dict[str, Any]:
        try:
            import subprocess
            import sys
            import os
            env = os.environ.copy()
            env["PYTHONPATH"] = str(self.repo_root / "src")
            subprocess.run([sys.executable, "-m", "deep.cli.main", "branch", name], cwd=self.repo_root, env=env, check=True)
            self._invalidate("tree", "work")
            self._log_activity("branch_created", f"{author} created branch {name}")
            return {"message": f"Branch {name} created"}
        except subprocess.CalledProcessError as e:
            return {"error": f"Git engine error: {e}"}
        except Exception as e:
            return {"error": str(e)}

    def checkout_branch(self, name: str, author: str) -> Dict[str, Any]:
        try:
            import subprocess
            import sys
            import os
            env = os.environ.copy()
            env["PYTHONPATH"] = str(self.repo_root / "src")
            subprocess.run([sys.executable, "-m", "deep.cli.main", "checkout", name], cwd=self.repo_root, env=env, check=True)
            self._invalidate("tree", "work")
            self._log_activity("branch_checkout", f"{author} checked out branch {name}")
            return {"message": f"Switched to branch {name}"}
        except subprocess.CalledProcessError as e:
            return {"error": f"Git engine error: {e}"}
        except Exception as e:
            return {"error": str(e)}

    def _invalidate_pr_caches(self) -> None:
        """Invalidate all PR-related caches immediately."""
        keys_to_remove = [k for k in self._cache if k.startswith("prs:") or k in ("work",)]
        for k in keys_to_remove:
            self._cache.pop(k, None)
