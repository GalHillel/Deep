"""
deep.web.dashboard
~~~~~~~~~~~~~~~~~~~~~~
HTTP + WebSocket server for the DeepGit Web Dashboard.

Serves a single-page interactive DAG explorer and exposes REST API
endpoints for querying repository state.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import traceback
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from typing import Optional

from deep.storage.objects import read_object, Commit, Tree, Blob, Tag
from deep.core.refs import (
    resolve_head,
    list_branches,
    get_branch,
    log_history,
)
from deep.core.repository import DEEP_GIT_DIR


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

def _gather_log(dg_dir: Path, max_count: int = 500) -> list[dict]:
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
    """Return branches, HEAD, and tags."""
    head = resolve_head(dg_dir)
    branches = {}
    heads_dir = dg_dir / "refs" / "heads"
    if heads_dir.exists():
        for f in heads_dir.iterdir():
            if f.is_file():
                branches[f.name] = f.read_text().strip()

    tags = {}
    tags_dir = dg_dir / "refs" / "tags"
    if tags_dir.exists():
        for f in tags_dir.iterdir():
            if f.is_file():
                tags[f.name] = f.read_text().strip()

    # Detect current branch
    from deep.core.refs import get_current_branch
    current_branch = get_current_branch(dg_dir)

    return {
        "head": head,
        "current_branch": current_branch,
        "branches": branches,
        "tags": tags,
    }


def _gather_multi_repo_data(repo_root: Path) -> list[dict]:
    """Scan siblings for DeepGit repos and return summaries."""
    repos = []
    try:
        parent = repo_root.parent
        for path in parent.iterdir():
            if path.is_dir():
                dg_dir = path / DEEP_GIT_DIR
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

    info: dict = {"sha": sha, "type": obj.OBJ_TYPE}
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
        # Fallback to main repo if no repo parameter is provided
        from deep.core.repository import DEEP_GIT_DIR
        return repo_root / DEEP_GIT_DIR
    
    from deep.core.repository import DEEP_GIT_DIR
    # Ensure relative path doesn't contain traversal
    repos_base = (repo_root / "repos").resolve()
    target_repo_dir = (repos_base / repo_name).resolve()
    
    if not target_repo_dir.is_relative_to(repos_base):
        raise ValueError("Security Violation: Path traversal detected in repo parameter")
    
    return target_repo_dir / DEEP_GIT_DIR

STATIC_DIR = Path(__file__).parent / "static"


class DashboardHandler(SimpleHTTPRequestHandler):
    """Serve the Web Dashboard SPA and REST API."""

    dg_dir: Path  # set at class level before starting server
    repo_root: Path # set at class level for multi-repo support

    def do_GET(self):
        try:
            self._handle_get()
        except Exception as e:
            try:
                body = json.dumps({"error": str(e)}).encode("utf-8")
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except Exception:
                pass

    def _handle_get(self):
        if self.path == "/" or self.path == "/index.html":
            self._serve_file(STATIC_DIR / "index.html", "text/html")
        elif self.path.startswith("/api/log"):
            from urllib.parse import urlparse, parse_qs
            repo_name = parse_qs(urlparse(self.path).query).get("repo", [None])[0]
            dg = _get_repo_dg_dir(self.repo_root, repo_name)
            self._json_response(_gather_log(dg))
        elif self.path.startswith("/api/refs"):
            from urllib.parse import urlparse, parse_qs
            repo_name = parse_qs(urlparse(self.path).query).get("repo", [None])[0]
            dg = _get_repo_dg_dir(self.repo_root, repo_name)
            self._json_response(_gather_refs(dg))
        elif self.path.startswith("/api/object/"):
            sha = self.path.split("/")[-1]
            from urllib.parse import urlparse, parse_qs
            repo_name = parse_qs(urlparse(self.path).query).get("repo", [None])[0]
            dg = _get_repo_dg_dir(self.repo_root, repo_name)
            self._json_response(_object_detail(dg, sha))
        elif self.path == "/api/repos":
            from deep.platform.platform import PlatformManager
            manager = PlatformManager(self.repo_root)
            repos = manager.list_repos()
            res = []
            for r in repos:
                dg = self.repo_root / "repos" / r / DEEP_GIT_DIR
                head = resolve_head(dg)
                res.append({"name": r, "head": head[:7] if head else "none"})
            self._json_response(res)

        # ── Collaboration API placeholders ──────────────────────────
        elif self.path.startswith("/api/issues"):
            from urllib.parse import urlparse, parse_qs
            repo_name = parse_qs(urlparse(self.path).query).get("repo", [None])[0]
            dg = (self.repo_root / "repos" / repo_name / DEEP_GIT_DIR) if repo_name else self.dg_dir
            from deep.core.issue import IssueManager
            im = IssueManager(dg)
            self._json_response([{"id": i.id, "title": i.title} for i in im.list_issues()])
        elif self.path.startswith("/api/prs"):
            from urllib.parse import urlparse, parse_qs
            repo_name = parse_qs(urlparse(self.path).query).get("repo", [None])[0]
            dg = (self.repo_root / "repos" / repo_name / DEEP_GIT_DIR) if repo_name else self.dg_dir
            from deep.core.pr import PRManager
            prm = PRManager(dg)
            self._json_response([{"id": p.id, "title": p.title} for p in prm.list_prs()])

        elif self.path == "/api/multi-repo":
            self._json_response(_gather_multi_repo_data(self.repo_root))

        # ── Heatmap API ─────────────────────────────────────────────
        elif self.path == "/api/heatmap":
            from deep.ai.analyzer import score_complexity
            from deep.storage.index import read_index
            heatmap = []
            objects_dir = self.dg_dir / "objects"
            index = read_index(self.dg_dir)
            for path, entry in index.entries.items():
                try:
                    obj = read_object(objects_dir, entry.sha)
                    if isinstance(obj, Blob):
                        content = obj.data.decode("utf-8", errors="replace")
                        comp = score_complexity(content)
                        heatmap.append({"file": path, "complexity": comp, "lines": len(content.splitlines())})
                except Exception: pass
            self._json_response(heatmap)

        elif self.path.startswith("/api/diff/"):
            sha = self.path.split("/")[-1].split("?")[0]
            from urllib.parse import urlparse, parse_qs
            repo_name = parse_qs(urlparse(self.path).query).get("repo", [None])[0]
            dg = _get_repo_dg_dir(self.repo_root, repo_name)
            self._json_response(_commit_diff(dg, sha))

        elif self.path.startswith("/api/history"):
            sha = self.path.split("/")[-1]
            self._json_response(_commit_diff(self.dg_dir, sha))
        elif self.path.startswith("/api/search"):
            # /api/search?q=pattern
            from urllib.parse import urlparse, parse_qs
            query = parse_qs(urlparse(self.path).query).get("q", [""])[0]
            from deep.core.search import search_history
            res = search_history(self.dg_dir, query)
            self._json_response([
                {
                    "commit_sha": r.commit_sha,
                    "rel_path": r.rel_path,
                    "line_num": r.line_num,
                    "content": r.content
                } for r in res
            ])
        elif self.path == "/api/metrics":
            self._json_response(self._load_metrics())
        elif self.path.startswith("/api/p2p/nodes"):
            from deep.network.p2p import P2PEngine
            from dataclasses import asdict
            engine = P2PEngine(self.dg_dir)
            self._json_response([asdict(p) for p in engine.get_peers()])
        elif self.path == "/api/p2p/presence":
            from deep.network.p2p import P2PEngine
            engine = P2PEngine(self.dg_dir)
            peers = engine.get_peers()
            presence = {}
            for p in peers:
                presence.update(p.presence)
            self._json_response(presence)
        elif self.path == "/api/dag-3d":
            # Return 3D coordinates for the DAG (X=time, Y=branch, Z=depth)
            log = _gather_log(self.dg_dir)
            branches = _gather_refs(self.dg_dir)["branches"]
            branch_map = {sha: name for name, sha in branches.items()}
            
            nodes_3d = []
            for i, entry in enumerate(log):
                branch_idx = list(branches.values()).index(entry["sha"]) if entry["sha"] in branches.values() else 0
                nodes_3d.append({
                    "sha": entry["sha"],
                    "x": i * 10,
                    "y": branch_idx * 20,
                    "z": len(entry["parents"]) * 5,
                    "message": entry["message"]
                })
            self._json_response(nodes_3d)
        elif self.path.startswith("/api/blame/"):
            rel_path = self.path[len("/api/blame/"):]
            from deep.core.blame import get_blame
            hunks = get_blame(self.dg_dir, rel_path)
            self._json_response([
                {
                    "commit_sha": h.commit_sha,
                    "author": h.author,
                    "timestamp": h.timestamp,
                    "start_line": h.start_line,
                    "num_lines": h.num_lines
                } for h in hunks
            ])
        elif self.path == "/api/heatmap":
            self._json_response(self._calculate_heatmap())
        elif self.path == "/api/ai/review":
            from deep.ai.assistant import DeepGitAI
            ai = DeepGitAI(self.dg_dir.parent)
            res = ai.review_changes()
            self._json_response({
                "text": res.text,
                "confidence": res.confidence,
                "details": res.details,
                "latency_ms": res.latency_ms
            })
        elif self.path == "/api/ai/metrics":
            from deep.ai.assistant import DeepGitAI
            ai = DeepGitAI(self.dg_dir.parent)
            self._json_response(ai.get_metrics())
        else:
            # Try to serve static file
            fpath = STATIC_DIR / self.path.lstrip("/")
            if fpath.exists() and fpath.is_file():
                ctype = "text/css" if fpath.suffix == ".css" else \
                        "application/javascript" if fpath.suffix == ".js" else \
                        "text/html"
                self._serve_file(fpath, ctype)
            else:
                self.send_error(404)

    def _json_response(self, data):
        body = json.dumps(data, default=str).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

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
        from deep.core.refs import resolve_head
        from deep.storage.objects import read_object, Commit
        
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
                obj = read_object(self.dg_dir / "objects", sha)
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
    dg_dir = repo_root / DEEP_GIT_DIR
    DashboardHandler.dg_dir = dg_dir
    DashboardHandler.repo_root = repo_root

    server = HTTPServer((host, port), DashboardHandler)
    print(f"DeepGit Dashboard running at http://{host}:{port}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDashboard stopped.")
    finally:
        server.server_close()
