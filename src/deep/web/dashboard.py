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
from deep.web.services import DashboardService

STATIC_DIR = Path(__file__).parent / "static"

class DashboardHandler(SimpleHTTPRequestHandler):
    """Serve the Web Dashboard SPA and REST API."""

    repo_root: ClassVar[Path]
    service: ClassVar[DashboardService]

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
            path = parsed.path.rstrip("/")
            qs = {k: v[0] for k, v in parse_qs(parsed.query).items()}

            if path == "" or path == "/index.html":
                return self._serve_file(STATIC_DIR / "index.html", "text/html")

            if path == "/api/tree": return self.send_json(self.service.get_tree())
            
            if path == "/api/file":
                filepath = qs.get("path")
                if not filepath: return self.send_json({"success": False, "error": "Missing path"}, 400)
                decoded_path = urllib.parse.unquote(filepath)
                return self.send_json(self.service.get_file_content(decoded_path))
                
            if path == "/api/graph": return self.send_json(self.service.get_graph())
            if path == "/api/status": return self.send_json(self.service.get_full_status())
            if path == "/api/diff": return self.send_json(self.service.get_diff())
            if path == "/api/prs/local": return self.send_json(self.service.get_prs_local())
            if path == "/api/issues/local": return self.send_json(self.service.get_issues_local())

            if path.startswith("/api/"):
                return self.send_json({"success": False, "error": f"API route not found: {path}"}, 404)

            fpath = STATIC_DIR / path.lstrip("/")
            if fpath.exists() and fpath.is_file():
                ctype = "text/css" if fpath.suffix == ".css" else \
                        "application/javascript" if fpath.suffix == ".js" else \
                        "text/plain"
                return self._serve_file(fpath, ctype)
            
            return self.send_error(404)
        except Exception as e:
            traceback.print_exc()
            return self.send_json({"success": False, "error": f"Server GET Error: {str(e)}"}, 500)

    def do_POST(self):
        try:
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/")
            content_length = int(self.headers.get("Content-Length", 0))
            body = {}
            if content_length > 0:
                try:
                    body = json.loads(self.rfile.read(content_length).decode("utf-8"))
                except Exception:
                    return self.send_json({"success": False, "error": "Invalid JSON"}, 400)

            # FINAL ROUTES
            if path == "/api/commit": return self.send_json(self.service.commit_enhanced(body))
            if path == "/api/item/create": return self.send_json(self.service.create_item(body.get("path"), body.get("type")))
            if path == "/api/file/save": return self.send_json(self.service.save_file_only(body.get("filepath") or body.get("path", ""), body.get("content", "")))
            if path == "/api/stage": return self.send_json(self.service.stage_file(body.get("filepath")))
            if path == "/api/unstage": return self.send_json(self.service.unstage_file(body.get("filepath")))
            if path == "/api/branch/checkout": return self.send_json(self.service.checkout_branch_forced(body.get("branch") or body.get("name", "")))
            if path == "/api/branch/create": return self.send_json(self.service.create_branch(body.get("name", "")))
            if path == "/api/merge": return self.send_json(self.service.merge_branch(body.get("branch") or body.get("name", "")))
            if path == "/api/pr/create": return self.send_json(self.service.create_pr_enhanced(body))
            if path == "/api/pr/review": return self.send_json(self.service.review_pr(body))
            if path == "/api/pr/merge": return self.send_json(self.service.merge_local_pr(body))
            if path == "/api/issue/create": return self.send_json(self.service.create_issue(body))
            if path == "/api/issue/manage": return self.send_json(self.service.manage_issue(body))

            return self.send_error(404)
        except Exception as e:
            traceback.print_exc()
            return self.send_json({"success": False, "error": f"Server POST Error: {str(e)}"}, 500)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

def start_dashboard(repo_root: Path, host: str = "127.0.0.1", port: int = 9000):
    """Start the Web Dashboard HTTP server."""
    dg_dir = repo_root / DEEP_DIR
    DashboardHandler.repo_root = repo_root
    DashboardHandler.service = DashboardService(dg_dir, repo_root)

    server = ThreadingHTTPServer((host, port), DashboardHandler)
    print(f"Deep Studio (Final) running at http://{host}:{port}")
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()
