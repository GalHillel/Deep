"""
deep.web.dashboard
~~~~~~~~~~~~~~~~~~~~~~
HTTP server for the Deep Web Dashboard (Final Overhaul).
"""

from __future__ import annotations
import json
import os
import traceback
import urllib.parse
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from typing import ClassVar, Any

from deep.core.constants import DEEP_DIR
from deep.core.errors import DeepCLIException
from deep.web.services import DashboardService

STATIC_DIR = Path(__file__).parent / "static"

class DashboardHandler(SimpleHTTPRequestHandler):
    """Serve the Web Dashboard SPA and REST API."""

    repo_root: ClassVar[Path]

    def get_service(self) -> DashboardService:
        """Create a new service instance per request for thread safety."""
        dg_dir = self.repo_root / DEEP_DIR
        return DashboardService(dg_dir, self.repo_root)

    def log_message(self, format, *args):
        """Mute standard HTTP logging to keep terminal clean."""
        pass

    def send_json(self, data: dict[str, Any], status: int = 200):
        """Standard JSON response sender with error awareness."""
        try:
            body = json.dumps(data, default=str).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            print(f"CRITICAL: Failed to send JSON response: {e}")

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

    def do_GET(self):
        try:
            parsed = urlparse(self.path)
            path = parsed.path.lower().rstrip("/")
            if not path: path = "/"
            qs = {k: v[0] for k, v in parse_qs(parsed.query).items()}

            # V2 SAFE CALL HELPER
            def _call_v2_safe(v2_fn, v1_fn, *args, **kwargs):
                try:
                    return v2_fn(*args, **kwargs)
                except Exception as e:
                    print(f"[web] V2 backend failed, falling back to V1: {e}")
                    return v1_fn(*args, **kwargs)

            if path == "" or path == "/" or path == "/index.html":
                return self._serve_file(STATIC_DIR / "index.html", "text/html")
            elif path == "/api/health": return self.send_json({"success": True, "status": "healthy"})
            elif path == "/api/work": return self.send_json(self.get_service().get_full_status())
            elif path == "/api/tree": return self.send_json(self.get_service().get_tree())
            elif path == "/api/prs/local": return self.send_json(self.get_service().get_prs_local())
            elif path == "/api/issues/local": return self.send_json(self.get_service().get_issues_local())
            elif path == "/api/file":
                filepath = qs.get("path")
                if not filepath: return self.send_json({"success": False, "error": "Missing path"}, 400)
                decoded_path = urllib.parse.unquote(filepath)
                # Security: Path Traversal hardening
                try:
                    (self.repo_root / decoded_path.lstrip("/")).resolve().relative_to(self.repo_root.resolve())
                except ValueError:
                    return self.send_json({"success": False, "error": "Path traversal denied"}, 403)
                return self.send_json(self.get_service().get_file_content(decoded_path))
            
            # --- V2 DEFAULT ENDPOINTS ---
            elif path == "/api/graph": 
                svc = self.get_service()
                return self.send_json(_call_v2_safe(svc.get_graph_v2, svc.get_graph))
            elif path == "/api/branches": 
                svc = self.get_service()
                return self.send_json(_call_v2_safe(svc.get_branches_v2, svc.get_branches_list))
            elif path == "/api/diff": 
                svc = self.get_service()
                sha = qs.get("sha")
                diff_path = qs.get("path")
                if diff_path:
                    try:
                        (self.repo_root / diff_path.lstrip("/")).resolve().relative_to(self.repo_root.resolve())
                    except ValueError:
                        return self.send_json({"success": False, "error": "Path traversal denied"}, 403)
                if sha:
                    from deep.storage.objects import read_object, Commit
                    try:
                        commit = read_object(svc.dg_dir / "objects", sha)
                        if commit.parent_shas:
                            return self.send_json(_call_v2_safe(svc.get_diff_v2, svc.get_diff, commit.parent_shas[0], sha))
                    except: pass
                return self.send_json(svc.get_diff(sha, diff_path))

            # --- EXPLICIT V2 ENDPOINTS ---
            elif path == "/api/v2/commits": return self.send_json(self.get_service().get_graph_v2())
            elif path == "/api/v2/branches": return self.send_json(self.get_service().get_branches_v2())
            elif path == "/api/v2/diff": return self.send_json(self.get_service().get_diff_v2(qs.get("sha1", ""), qs.get("sha2", "")))

            # --- LEGACY DETAILS ---
            elif path == "/api/commit/details": 
                svc = self.get_service()
                return self.send_json(_call_v2_safe(svc.get_commit_details_v2, svc.get_commit_details, qs.get("sha", "")))
            elif path == "/api/status": return self.send_json(self.get_service().get_full_status())
            elif path == "/api/ai/suggest":
                from deep.web.services import api_ai_suggest
                return self.send_json(api_ai_suggest())
            elif path.startswith("/api/"):
                return self.send_json({"success": False, "error": f"API route not found: {path}"}, 404)

            fpath = STATIC_DIR / path.lstrip("/")
            if fpath.exists() and fpath.is_file():
                ctype = "text/css" if fpath.suffix == ".css" else \
                        "application/javascript" if fpath.suffix == ".js" else \
                        "text/plain"
                return self._serve_file(fpath, ctype)
            
            return self.send_error(404)
        except (Exception, DeepCLIException) as e:
            traceback.print_exc()
            msg = getattr(e, "message", str(e)) if not isinstance(e, DeepCLIException) else f"CLI Exit {e.code}"
            return self.send_json({"success": False, "error": f"Server GET Error: {msg}"}, 500)

    def do_POST(self):
        try:
            parsed = urlparse(self.path)
            path = parsed.path.lower().strip().rstrip("/")
            if not path: path = "/"
            content_length = int(self.headers.get("Content-Length", 0))
            body = {}
            if content_length > 0:
                try:
                    body = json.loads(self.rfile.read(content_length).decode("utf-8"))
                except Exception:
                    return self.send_json({"success": False, "error": "Invalid JSON"}, 400)

            # FINAL ROUTES
            if path == "/api/commit":
                from deep.web.services import perform_commit
                return self.send_json(perform_commit(body.get("filepath"), body.get("content"), body.get("message"), body.get("amend", False)))
            elif "/api/stash/push" in path:
                from deep.web.services import api_stash_push
                return self.send_json(api_stash_push(body))
            elif "/api/stash/pop" in path:
                from deep.web.services import api_stash_pop
                return self.send_json(api_stash_pop(body))
            elif path == "/api/item/create": return self.send_json(self.get_service().create_item(body.get("path"), body.get("type")))
            elif path == "/api/file/save": 
                filepath = body.get("filepath") or body.get("path", "")
                try:
                    (self.repo_root / filepath.lstrip("/")).resolve().relative_to(self.repo_root.resolve())
                except ValueError:
                    return self.send_json({"success": False, "error": "Path traversal denied"}, 403)
                return self.send_json(self.get_service().save_file_only(filepath, body.get("content", "")))
            elif path == "/api/stage": 
                from deep.web.services import api_stage_file
                return self.send_json(api_stage_file(body))
            elif path == "/api/unstage": 
                from deep.web.services import api_unstage_file
                return self.send_json(api_unstage_file(body))
            elif path == '/api/unstage_all':
                from deep.web.services import api_unstage_all
                return self.send_json(api_unstage_all())
            elif path == '/api/discard':
                from deep.web.services import api_discard_file
                return self.send_json(api_discard_file(body.get('filepath')))
            elif path == '/api/discard_all':
                from deep.web.services import api_discard_all
                return self.send_json(api_discard_all())
            elif path == "/api/branch/checkout": return self.send_json(self.get_service().checkout_branch_forced(body.get("branch") or body.get("name", "")))
            elif path == "/api/branch/create": return self.send_json(self.get_service().create_branch(body.get("name", "")))
            elif path == "/api/merge": return self.send_json(self.get_service().merge_branch(body.get("branch") or body.get("name", "")))
            elif path == "/api/pr/create": return self.send_json(self.get_service().create_pr_enhanced(body))
            elif path == "/api/pr/review": return self.send_json(self.get_service().review_pr(body))
            elif path == "/api/pr/merge": return self.send_json(self.get_service().merge_local_pr(body))
            elif path == "/api/pr/comment": return self.send_json(self.get_service().add_pr_comment(body))
            elif path == "/api/pr/reply": return self.send_json(self.get_service().add_pr_reply(body))
            elif path == "/api/pr/resolve": return self.send_json(self.get_service().resolve_pr_thread(body))
            elif path == "/api/issue/create": return self.send_json(self.get_service().create_issue(body))
            elif path == "/api/issue/manage": return self.send_json(self.get_service().manage_issue(body))
            elif path == "/api/item/create": return self.send_json(self.get_service().create_item(body.get("path"), body.get("type")))
            elif path == "/api/item/rename": return self.send_json(self.get_service().rename_item(body.get("path"), body.get("new_name")))
            elif path == "/api/item/delete": return self.send_json(self.get_service().delete_item(body.get("path")))
            elif path == '/api/language/format':
                from deep.web.services import api_lang_format
                return self.send_json(api_lang_format(body.get('code', ''), body.get('language', '')))
            elif path == '/api/language/analyze':
                from deep.web.services import api_lang_analyze
                return self.send_json(api_lang_analyze(body.get('code', ''), body.get('language', '')))
            elif path == '/api/language/complete':
                from deep.web.services import api_lang_complete
                return self.send_json(api_lang_complete(body))
            elif path == '/api/language/definition':
                from deep.web.services import api_lang_definition
                return self.send_json(api_lang_definition(body))
            elif path.startswith("/api/"):
                return self.send_json({"success": False, "error": f"API POST route not found: {path}"}, 404)
        except (Exception, DeepCLIException) as e:
            traceback.print_exc()
            msg = getattr(e, "message", str(e)) if not isinstance(e, DeepCLIException) else f"CLI Exit {e.code}"
            return self.send_json({"success": False, "error": f"Server POST Error: {msg}"}, 500)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

def _tree_entries_flat(objects_dir, tree_sha, prefix=""):
    """Helper used by AI and search to get a flat list of tree entries."""
    from deep.storage.objects import read_object, Tree
    entries = {}
    try:
        tree = read_object(objects_dir, tree_sha)
        if not isinstance(tree, Tree): return {}
        for entry in tree.entries:
            full_name = f"{prefix}/{entry.name}" if prefix else entry.name
            if entry.mode == "40000": # Directory
                entries.update(_tree_entries_flat(objects_dir, entry.sha, full_name))
            else:
                entries[full_name] = entry.sha
    except Exception: pass
    return entries

def _get_repo_dg_dir(base_dir: Path, repo_name: str) -> Path:
    """Security helper to resolve repository .deep directory from a base path."""
    # Prevent basic traversals and normalize
    safe_name = repo_name.lstrip('/').replace('\\', '/')
    repo_path = (base_dir / safe_name).resolve()
    base_resolved = base_dir.resolve()
    
    # Crucial Security Check: Ensure the resolved path stays within base_dir
    if not str(repo_path).startswith(str(base_resolved)):
        raise ValueError("Security Violation: Path traversal detected")
        
    return repo_path / DEEP_DIR

def start_dashboard(repo_root: Path, host: str = "127.0.0.1", port: int = 9000):
    """Start the Web Dashboard HTTP server."""
    DashboardHandler.repo_root = repo_root

    server = ThreadingHTTPServer((host, port), DashboardHandler)
    print(f"Deep Studio (Final) running at http://{host}:{port}")
    print("[web] using snapshot backend (v2 default with v1 fallback)")
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()
