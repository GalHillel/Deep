"""
deep.web.dashboard
~~~~~~~~~~~~~~~~~~~~~~
HTTP server for the Deep Web Dashboard.

Serves a single-page interactive Developer Platform UI and exposes
REST API endpoints for querying and mutating repository state.
All data access goes through DashboardService — no direct file access here.
"""

from __future__ import annotations

import json
import os
import traceback
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from typing import Optional, ClassVar, Any, cast
from urllib.parse import urlparse, parse_qs

from deep.storage.objects import read_object, Commit, Tree, Blob, Tag  # type: ignore[import]
from deep.core.refs import resolve_head, list_branches, get_branch, list_tags  # type: ignore[import]
from deep.core.repository import find_repo  # type: ignore[import]
from deep.core.constants import DEEP_DIR  # type: ignore[import]
from deep.storage.index import read_index  # type: ignore[import]
from deep.core.search import search_history  # type: ignore[import]
from deep.web.services import DashboardService  # type: ignore[import]
from deep.ai.assistant import DeepAI  # type: ignore[import]


def _tree_entries_flat(objects_dir: Path, tree_sha: str, prefix: str = "") -> dict[str, str]:
    """Flatten a tree into {path: sha} dict."""
    result: dict[str, str] = {}
    try:
        obj = read_object(objects_dir, tree_sha)
    except Exception:
        return result
    if not isinstance(obj, Tree):
        return result
    for entry in obj.entries:
        full = f"{prefix}{entry.name}" if not prefix else f"{prefix}/{entry.name}"
        if entry.mode.startswith("40"):  # subtree
            result.update(_tree_entries_flat(objects_dir, entry.sha, full))
        else:
            result[full] = entry.sha
    return result


# ── REST API Helpers ─────────────────────────────────────────────────

def _gather_log(dg_dir: Path, max_count: int = 300) -> list[dict]:
    """Walk the commit DAG and return a serialisable list."""
    head_sha = resolve_head(dg_dir)
    if not head_sha:
        return []

    visited: set[str] = set()
    result: list[dict] = []
    queue = [head_sha]

    while queue and len(result) < max_count:
        sha = queue.pop(0)
        if sha in visited:
            continue
        visited.add(sha)

        try:
            obj = read_object(dg_dir / "objects", sha)
        except Exception:
            continue

        if not isinstance(obj, Commit):
            continue

        result.append({
            "sha": sha,
            "message": obj.message.strip(),
            "author": obj.author,
            "email": "",
            "timestamp": obj.timestamp,
            "parents": obj.parent_shas,
            "tree_sha": obj.tree_sha,
        })
        queue.extend(obj.parent_shas)

    return result


def _gather_refs(dg_dir: Path) -> dict:
    """Return branches, HEAD, and tags. Production-grade ref loader."""
    import re
    SHA_RE = re.compile(r"^[0-9a-f]{40}$")

    head = resolve_head(dg_dir)
    branches = {}
    heads_dir = dg_dir / "refs" / "heads"
    
    if heads_dir.exists():
        for f in heads_dir.iterdir():
            if not f.is_file():
                continue
            
            # Phase 1: Fix critical checkout bug - ignore locks, tmps, logs
            if f.suffix in ('.lock', '.tmp', '.log') or f.name.endswith('.lock'):
                continue
                
            content = f.read_text().strip()
            
            # Validate SHA format - NEVER treat JSON or garbage as SHA
            if SHA_RE.match(content):
                branches[f.name] = content

    tags = {}
    tags_dir = dg_dir / "refs" / "tags"
    if tags_dir.exists():
        for f in tags_dir.iterdir():
            if f.is_file() and not f.name.endswith('.lock'):
                content = f.read_text().strip()
                if SHA_RE.match(content):
                    tags[f.name] = content

    from deep.core.refs import get_current_branch  # type: ignore
    current_branch = get_current_branch(dg_dir)

    return {
        "head": head,
        "current_branch": current_branch,
        "branches": branches,
        "tags": tags,
    }


def _gather_multi_repo_data(repo_root: Path) -> list[dict]:
    """Scan siblings for Deep repos and return summaries."""
    repos = []
    try:
        parent = repo_root.parent
        for path in parent.iterdir():
            if path.is_dir():
                dg_dir = path / DEEP_DIR
                if dg_dir.exists():
                    head = resolve_head(dg_dir)
                    repos.append({
                        "name": path.name,
                        "path": str(path),
                        "head": head[:7] if head else "unborn",
                        "branches": len(list_branches(dg_dir))
                    })
    except Exception:
        pass
    return repos


def _object_detail(dg_dir: Path, sha: str) -> dict:
    """Return detailed info about an object."""
    try:
        obj = read_object(dg_dir / "objects", sha)
    except Exception as e:
        return {"error": str(e)}

    info: dict = {"sha": sha, "type": cast(Any, obj).OBJ_TYPE}  # type: ignore
    if isinstance(obj, Commit):
        info.update({
            "message": obj.message.strip(),
            "author": obj.author,
            "email": "",
            "timestamp": obj.timestamp,
            "parents": obj.parent_shas,
            "tree_sha": obj.tree_sha,
        })
    elif isinstance(obj, Tree):
        info["entries"] = [
            {"mode": e.mode, "name": e.name, "sha": e.sha}
            for e in obj.entries
        ]
    elif isinstance(obj, Blob):
        try:
            info["content"] = obj.data.decode("utf-8", errors="replace")[:4000]
        except Exception:
            info["content"] = "<binary>"
    elif isinstance(obj, Tag):
        info.update({
            "tag_name": obj.tag_name,
            "target_sha": obj.target_sha,
            "message": obj.message.strip() if obj.message else "",
        })

    return info


def _commit_diff(dg_dir: Path, sha: str) -> list[dict]:
    """Return the diff for a single commit."""
    try:
        obj = read_object(dg_dir / "objects", sha)
    except Exception:
        return []
    if not isinstance(obj, Commit):
        return []

    objects_dir = dg_dir / "objects"
    parent_entries: dict[str, str] = {}
    if obj.parent_shas:
        try:
            parent = read_object(objects_dir, obj.parent_shas[0])
            if isinstance(parent, Commit):
                parent_entries = _tree_entries_flat(objects_dir, parent.tree_sha)
        except Exception:
            pass

    current_entries = _tree_entries_flat(objects_dir, obj.tree_sha)

    result = []
    all_paths = set(parent_entries.keys()) | set(current_entries.keys())
    for path in sorted(all_paths):
        old_sha = parent_entries.get(path)
        new_sha = current_entries.get(path)
        if old_sha and not new_sha:
            result.append({"path": path, "status": "deleted", "old_sha": old_sha, "new_sha": ""})
        elif not old_sha and new_sha:
            result.append({"path": path, "status": "added", "old_sha": "", "new_sha": new_sha})
        elif old_sha != new_sha:
            result.append({"path": path, "status": "modified", "old_sha": old_sha or "", "new_sha": new_sha or ""})
    return result


# ── HTTP Handler ─────────────────────────────────────────────────────

def _get_repo_dg_dir(repo_root: Path, repo_name: Optional[str]) -> Path:
    """Safely resolve repository DG_DIR and prevent path traversal."""
    if not repo_name:
        return repo_root / DEEP_DIR

    repos_base = (repo_root / "repos").resolve()
    target_repo_dir = (repos_base / repo_name).resolve()

    if not target_repo_dir.is_relative_to(repos_base):
        raise ValueError("Security Violation: Path traversal detected in repo parameter")

    return target_repo_dir / DEEP_DIR


STATIC_DIR = Path(__file__).parent / "static"


class DashboardHandler(SimpleHTTPRequestHandler):
    """Serve the Web Dashboard SPA and REST API."""

    dg_dir: ClassVar[Path]
    repo_root: ClassVar[Path]
    service: ClassVar[DashboardService]

    # ── GET ───────────────────────────────────────────────────────

    def do_GET(self):
        try:
            self._handle_get()
        except Exception as e:
            self._error(500, str(e))

    def _handle_get(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        qs = {k: v[0] for k, v in parse_qs(parsed.query).items()}

        # ── Static files ────────────────────────────────────────
        if path == "" or path == "/index.html":
            self._serve_file(STATIC_DIR / "index.html", "text/html")
            return

        # ── API Routes (GET) ────────────────────────────────────
        
        # 1. System & Metadata
        if path == "/api/health":
            return self._send_res(self.service.get_health())
        if path == "/api/activity":
            return self._send_res(self.service.get_activity())
        
        # 2. Git Data (Core)
        if path == "/api/log":
            dg = _get_repo_dg_dir(self.repo_root, qs.get("repo"))
            try:
                data = _gather_log(dg)
                return self._send_res({"success": True, "data": data})
            except Exception as e:
                return self._error(500, f"Failed to gather log: {str(e)}")

        if path == "/api/refs":
            dg = _get_repo_dg_dir(self.repo_root, qs.get("repo"))
            try:
                data = _gather_refs(dg)
                return self._send_res({"success": True, "data": data})
            except Exception as e:
                return self._error(500, f"Failed to gather refs: {str(e)}")

        if path.startswith("/api/object/"):
            sha = path.split("/")[-1]
            dg = _get_repo_dg_dir(self.repo_root, qs.get("repo"))
            try:
                data = _object_detail(dg, sha)
                if "error" in data:
                    return self._send_res({"success": False, "error": data["error"]})
                return self._send_res({"success": True, "data": data})
            except Exception as e:
                return self._error(500, f"Failed to get object detail: {str(e)}")

        if path.startswith("/api/diff/"):
            sha = path.split("/")[-1]
            dg = _get_repo_dg_dir(self.repo_root, qs.get("repo"))
            try:
                data = _commit_diff(dg, sha)
                return self._send_res({"success": True, "data": data})
            except Exception as e:
                return self._error(500, f"Failed to get commit diff: {str(e)}")

        # 3. Workspace / IDE
        if path == "/api/tree":
            return self._send_res(self.service.get_tree())
        if path == "/api/file":
            filepath = qs.get("path")
            if not filepath: return self._error(400, "Missing path parameter")
            return self._send_res(self.service.get_file(filepath))
        if path == "/api/diff":
            filepath = qs.get("path")
            if not filepath: return self._error(400, "Missing path parameter")
            return self._send_res(self.service.get_diff(filepath, qs.get("base", "HEAD")))
        if path == "/api/status/full":
            return self._send_res(self.service.get_full_status())

        # 4. Pull Requests
        if path == "/api/prs":
            return self._send_res(self.service.get_prs(status=qs.get("status"), author=qs.get("author")))
        if path.startswith("/api/pr/"):
            m = re.match(r"^/api/pr/(\d+)$", path)
            if m:
                pr_id = int(m.group(1))
                return self._send_res(self.service.get_pr_detail(pr_id))

        # 5. Issues
        if path == "/api/issues":
            return self._send_res(self.service.get_issues(type_filter=qs.get("type"), status=qs.get("status")))
        
        # 6. Work Context
        if path == "/api/work":
            return self._send_res(self.service.get_work())

        # ── Fallback ───────────────────────────────────────────
        fpath = STATIC_DIR / path.lstrip("/")
        if fpath.exists() and fpath.is_file():
            ctype = "text/css" if fpath.suffix == ".css" else \
                    "application/javascript" if fpath.suffix == ".js" else \
                    "text/html"
            self._serve_file(fpath, ctype)
        else:
            self.send_error(404)

    # ── POST ──────────────────────────────────────────────────────

    def do_POST(self):
        try:
            self._handle_post()
        except Exception as e:
            self._error(500, str(e))

    def _handle_post(self):
        path = urlparse(self.path).path.rstrip("/")
        
        # Safe JSON body parsing
        content_length = int(self.headers.get("Content-Length", 0))
        body = {}
        if content_length > 0:
            try:
                body = json.loads(self.rfile.read(content_length).decode("utf-8"))
            except Exception:
                return self._error(400, "Invalid JSON body")

        author = body.get("author", "WebIDE")

        # 1. File Actions
        if path == "/api/file/save":
            return self._send_res(self.service.save_file(body.get("path", ""), body.get("content", "")))
        
        if path == "/api/file/add":
            return self._send_res(self.service.add_file(body.get("path", "")))

        if path == "/api/file/create":
            return self._send_res(self.service.create_file(body.get("path", ""), author))

        if path == "/api/file/delete":
            return self._send_res(self.service.delete_file(body.get("path", ""), author))

        # 2. Git Actions
        if path == "/api/commit":
            return self._send_res(self.service.commit(body.get("message", "IDE update"), author))

        if path == "/api/generate/commit-msg":
            ai = DeepAI(self.repo_root)
            res = ai.suggest_commit_message()
            return self._send_res({"success": True, "data": {"message": res.text, "confidence": res.confidence}})

        if path == "/api/branch/create":
            return self._send_res(self.service.create_branch(body.get("name", ""), author))

        if path == "/api/branch/checkout":
            return self._send_res(self.service.checkout_branch(body.get("name", ""), author))

        if path == "/api/reset":
            return self._send_res(self.service.reset_repo(body.get("mode", "mixed"), body.get("target", "HEAD")))
        
        if path == "/api/revert":
            return self._send_res(self.service.revert_commit(body.get("sha", ""), author))

        # 3. PR Actions
        m_pr = re.match(r"^/api/pr/(\d+)/(approve|request_changes|resolve_thread|merge)$", path)
        if m_pr:
            pr_id, action = int(m_pr.group(1)), m_pr.group(2)
            if action == "approve": return self._send_res(self.service.approve_pr(pr_id, author))
            if action == "request_changes": return self._send_res(self.service.request_changes_pr(pr_id, author, body.get("comment", "")))
            if action == "resolve_thread": return self._send_res(self.service.resolve_thread_pr(pr_id, int(body.get("thread_id", 0))))
            if action == "merge": return self._send_res(self.service.merge_pr(pr_id, author))

        # 4. Issue Actions
        if path == "/api/issues":
            return self._send_res(self.service.create_issue(body.get("title", ""), body.get("description", ""), body.get("type", "task"), author))
        
        m_iss = re.match(r"^/api/issues/(\d+)/close$", path)
        if m_iss:
            return self._send_res(self.service.close_issue(int(m_iss.group(1)), author))

        return self._error(404, f"Unknown endpoint: {path}")

    # ── Response helpers ──────────────────────────────────────────

    def _send_res(self, res: dict[str, Any]):
        """Unified response sender for service dicts."""
        body = json.dumps(res, default=str).encode("utf-8")
        status = 200 if res.get("success") else 422
        # Special case: 404 if data is empty/none for a detail endpoint (like PR)
        if res.get("success") and res.get("data") is None:
            status = 404
        
        self.send_response(status)
        self._headers(len(body))
        self.wfile.write(body)

    def _success(self, data: Any):
        """Legacy helper for non-service routes."""
        self._send_res({"success": True, "data": data})

    def _error(self, status: int, message: str):
        body = json.dumps({"success": False, "error": message}).encode("utf-8")
        self.send_response(status)
        self._headers(len(body))
        self.wfile.write(body)

    def _headers(self, length: int):
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(length))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_OPTIONS(self):
        """Handle CORS preflight requests."""
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _serve_file(self, path: Path, content_type: str):
        try:
            data = path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except Exception:
            self.send_error(500)

    def _load_metrics(self):
        metrics_file = self.dg_dir / "metrics.json"
        if metrics_file.exists():
            try:
                return json.loads(metrics_file.read_text())
            except Exception:
                pass
        return {}

    def _calculate_heatmap(self) -> dict:
        """Calculate commit density per day for the last 365 days."""
        counts = {}
        head = resolve_head(self.dg_dir)
        if not head:
            return counts

        visited = set()
        queue = [head]
        import datetime
        while queue:
            sha = queue.pop(0)
            if sha in visited:
                continue
            visited.add(sha)

            try:
                obj = read_object(self.dg_dir / "objects", sha)  # type: ignore
                if isinstance(obj, Commit):
                    date_str = datetime.datetime.fromtimestamp(obj.timestamp).strftime("%Y-%m-%d")
                    counts[date_str] = counts.get(date_str, 0) + 1
                    queue.extend(obj.parent_shas)
            except Exception:
                continue
        return counts

    def log_message(self, format, *args):
        pass  # Suppress default logging


def start_dashboard(repo_root: Path, host: str = "127.0.0.1", port: int = 9000):
    """Start the Web Dashboard HTTP server."""
    dg_dir = repo_root / DEEP_DIR
    DashboardHandler.dg_dir = dg_dir
    DashboardHandler.repo_root = repo_root
    DashboardHandler.service = DashboardService(dg_dir, repo_root)

    server = ThreadingHTTPServer((host, port), DashboardHandler)
    print(f"Deep Dashboard running at http://{host}:{port}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDashboard stopped.")
    finally:
        server.server_close()
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Deep Platform Dashboard")
    parser.add_argument("--repo", type=str, default=".", help="Path to repository root")
    parser.add_argument("--port", type=int, default=9000, help="Port to run on")
    args = parser.parse_args()
    
    start_dashboard(Path(args.repo).absolute(), port=args.port)
