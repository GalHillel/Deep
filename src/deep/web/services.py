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

    def _get_cached(self, key: str, fn: Any) -> Any:
        """Generic caching wrapper."""
        cached = self._cache_get(key)
        if cached is not None:
            return cached
        data = fn()
        self._cache_set(key, data)
        return data

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
        def fetch():
            try:
                im = IssueManager(self.dg_dir)
                issues = im.list_issues()
                result = []
                for iss in issues:
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
                return result
            except Exception:
                return []

        cache_key = f"issues:{type_filter or ''}:{status or ''}"
        all_issues = self._get_cached(cache_key, fetch)
        
        if type_filter or status:
            return [i for i in all_issues if 
                    (not type_filter or i["type"] == type_filter) and 
                    (not status or i["status"] == status)]
        return all_issues

    def create_issue(self, title: str, description: str, type: str, author: str) -> Dict[str, Any]:
        try:
            im = IssueManager(self.dg_dir)
            issue = im.create_issue(title, description, type, author)
            self._invalidate_pr_caches()
            return {"message": f"Issue #{issue.id} created", "id": issue.id}
        except Exception as e:
            return {"error": str(e)}

    def close_issue(self, issue_id: int, author: str) -> Dict[str, Any]:
        try:
            im = IssueManager(self.dg_dir)
            im.close_issue(issue_id, author)
            self._invalidate_pr_caches()
            return {"message": f"Issue #{issue_id} closed"}
        except Exception as e:
            return {"error": str(e)}

    # ── Work snapshot ────────────────────────────────────────────────

    def get_work(self) -> Dict[str, Any]:
        """Returns complex work context: branch, staged, changed, active PR, related issue."""
        def fetch():
            current_branch = ""
            try:
                from deep.core.refs import get_current_branch
                current_branch = get_current_branch(self.dg_dir) or ""
            except Exception:
                pass

            # Staged / Changed files
            staged_files = []
            changed_files = []
            try:
                from deep.storage.index import read_index
                from deep.core.repository import get_status
                status = get_status(self.repo_root)
                staged_files = status.get('staged', [])
                changed_files = status.get('unstaged', [])
            except Exception:
                pass

            prs = self.get_prs()
            issues = self.get_issues()

            active_pr = next((p for p in prs if p["status"] == "open" and p["head"] == current_branch), None)
            related_issue = None
            if active_pr and active_pr.get("linked_issue"):
                related_issue = next((iss for iss in issues if iss["id"] == active_pr["linked_issue"]), None)

            return {
                "current_branch": current_branch,
                "staged_files": staged_files,
                "changed_files": changed_files,
                "active_pr": active_pr,
                "related_issue": related_issue,
                "open_prs": len([p for p in prs if p["status"] == "open"]),
                "open_issues": len([iss for iss in issues if iss["status"] == "open"]),
            }

        return self._get_cached("work", fetch)

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
        """Hierarchical tree builder with production-grade filters."""
        cache_key = "tree"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        import os

        # Standard excludes for a local dev platform
        EXCLUDES = {'.deep', '.git', 'node_modules', '__pycache__', '.pytest_cache', '.venv'}
        
        def build_node(dir_path: str, name: str) -> Dict[str, Any]:
            node = {"name": name, "type": "folder", "children": [], "path": dir_path}
            try:
                # Use listdir and filter
                entries = sorted(os.listdir(self.repo_root / dir_path) if dir_path else os.listdir(self.repo_root))
            except Exception:
                return node
                
            for entry in entries:
                if entry in EXCLUDES or entry.startswith('.lock') or entry.startswith('.tmp'):
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
        """Production binary detection: BOMs are NOT binary, null bytes are only allowed if BOM exists."""
        if not data:
            return False
            
        # Detect BOMs (UTF-16, UTF-8-SIG)
        if data.startswith((b'\xff\xfe', b'\xfe\xff', b'\xef\xbb\xbf')):
            return False
            
        # Heuristic: if null bytes exist without a BOM, it's likely binary
        # We check the first 8KB like git does
        chunk = data[:8192]
        return b'\x00' in chunk

    def _decode_file(self, raw_bytes: bytes) -> tuple[str, str]:
        """Robust decoding with encoding detection. Returns (content, encoding)."""
        # 1. UTF-8 with BOM
        if raw_bytes.startswith(b'\xef\xbb\xbf'):
            return raw_bytes.decode('utf-8-sig'), 'utf-8-sig'
            
        # 2. UTF-16 (Little Endian with BOM)
        if raw_bytes.startswith(b'\xff\xfe'):
            return raw_bytes.decode('utf-16'), 'utf-16'
            
        # 3. UTF-16 (Big Endian with BOM)
        if raw_bytes.startswith(b'\xfe\xff'):
            return raw_bytes.decode('utf-16'), 'utf-16'
            
        # 4. Standard UTF-8
        try:
            return raw_bytes.decode('utf-8'), 'utf-8'
        except UnicodeDecodeError:
            pass
            
        # 5. Fallback to latin-1 (never fails)
        return raw_bytes.decode('latin-1'), 'latin-1'

    def get_file(self, rel_path: str) -> Dict[str, Any]:
        """Premium file reader with encoding and binary detection."""
        MAX_FILE_SIZE = 2 * 1024 * 1024  # 2MB
        try:
            file_path = self._resolve_safe_path(rel_path)
            
            if not file_path.exists():
                return {
                    "content": "",
                    "path": rel_path,
                    "isNew": True,
                    "isBinary": False,
                    "encoding": "utf-8"
                }
                
            if not file_path.is_file():
                return {"error": f"Path is not a file: {rel_path}"}
            
            size = file_path.stat().st_size
            if size > MAX_FILE_SIZE:
                return {
                    "isBinary": True,
                    "content": f"File too large ({size//1024} KB). Max limit 2MB.",
                    "path": rel_path,
                    "encoding": "unknown"
                }

            with open(file_path, 'rb') as f:
                raw = f.read()

            is_binary = self._is_probably_binary(raw)
            if is_binary:
                return {
                    "isBinary": True,
                    "content": "Binary file cannot be displayed",
                    "path": rel_path,
                    "encoding": "binary"
                }

            content, encoding = self._decode_file(raw)
            return {
                "content": content,
                "path": rel_path,
                "size": size,
                "isBinary": False,
                "isNew": False,
                "encoding": encoding
            }
        except Exception as e:
            return {"error": str(e)}


    def save_file(self, rel_path: str, content: str) -> Dict[str, Any]:
        """Save file content without committing."""
        try:
            file_path = self._resolve_safe_path(rel_path)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            # All web saves are UTF-8
            file_path.write_text(content or "", encoding='utf-8')
            self._invalidate("tree", "work")
            return {"message": f"Saved {rel_path}"}
        except Exception as e:
            return {"error": str(e)}

    def add_file(self, rel_path: str) -> Dict[str, Any]:
        """Deep Add: stage a file."""
        import argparse
        try:
            from deep.commands.add_cmd import run as run_add
            run_add(argparse.Namespace(paths=[rel_path], dg_dir=self.dg_dir, repo_root=self.repo_root))
            self._invalidate("work")
            return {"message": f"Added {rel_path} to index"}
        except Exception as e:
            return {"error": str(e)}

    def commit(self, message: str, author: str) -> Dict[str, Any]:
        """Deep Commit: commit all staged changes."""
        import argparse
        try:
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
            self._log_activity("commit_created", f"{author} committed changes: {message}")
            return {"message": "Changes committed successfully"}
        except Exception as e:
            return {"error": str(e)}

    def save_and_commit(self, rel_path: str, content: str, message: str, author: str) -> Dict[str, Any]:
        """Legacy helper - combines save, add, and commit."""
        save_res = self.save_file(rel_path, content)
        if "error" in save_res: return save_res
        add_res = self.add_file(rel_path)
        if "error" in add_res: return add_res
        return self.commit(message, author)

    def create_file(self, rel_path: str, author: str) -> Dict[str, Any]:
        try:
            file_path = self._resolve_safe_path(rel_path)
            if file_path.exists():
                return {"error": "File already exists"}
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text("", encoding="utf-8")
            self._invalidate("tree", "work")
            self._log_activity("file_created", f"{author} created file {rel_path}")
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
            self._invalidate("tree", "work")
            self._log_activity("file_deleted", f"{author} deleted {rel_path}")
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
            self._invalidate("work")
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

    def delete_branch(self, name: str, author: str) -> Dict[str, Any]:
        try:
            import subprocess
            import sys
            import os
            env = os.environ.copy()
            env["PYTHONPATH"] = str(self.repo_root / "src")
            subprocess.run([sys.executable, "-m", "deep.cli.main", "branch", "-d", name], cwd=self.repo_root, env=env, check=True)
            self._invalidate("work")
            self._log_activity("branch_deleted", f"{author} deleted branch {name}")
            return {"message": f"Branch {name} deleted"}
        except subprocess.CalledProcessError as e:
            return {"error": f"Git engine error: {e}"}
        except Exception as e:
            return {"error": str(e)}

    def _invalidate_pr_caches(self) -> None:
        """Invalidate all PR-related caches immediately."""
        keys_to_remove = [k for k in self._cache if k.startswith("prs:") or k in ("work",)]
        for k in keys_to_remove:
            self._cache.pop(k, None)
