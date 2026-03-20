"""
deep.web.dashboard
~~~~~~~~~~~~~~~~~~~~~~
HTTP server for the Deep Web Dashboard (Pinnacle Upgrade).
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

    def _send_res(self, res: dict[str, Any], status: int = 200):
        """Unified response sender."""
        body = json.dumps(res, default=str).encode("utf-8")
        # Override status if explicitly provided or if success is False
        if not res.get("success", True) and status == 200:
            status = 422
            
        self.send_response(status)
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

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        # PINNACLE FIX: Safe multi-value extraction
        qs = {k: v[0] for k, v in parse_qs(parsed.query).items()}

        # Static files
        if path == "" or path == "/index.html":
            return self._serve_file(STATIC_DIR / "index.html", "text/html")

        # API Routes (GET)
        if path == "/api/tree": return self._send_res(self.service.get_tree())
        
        if path == "/api/file":
            filepath = qs.get("path")
            if not filepath: return self._send_res({"success": False, "error": "Missing path"}, 400)
            # PINNACLE FIX: Unquote path
            filepath = urllib.parse.unquote(filepath)
            return self._send_res(self.service.get_file(filepath))
            
        if path == "/api/graph": return self._send_res(self.service.get_graph())
        if path == "/api/status": return self._send_res(self.service.get_full_status())
        if path == "/api/diff": return self._send_res(self.service.get_diff())
        if path == "/api/prs/local": return self._send_res(self.service.get_prs_local())
        if path == "/api/issues/local": return self._send_res(self.service.get_issues_local())

        # Fallback for other static assets
        fpath = STATIC_DIR / path.lstrip("/")
        if fpath.exists() and fpath.is_file():
            ctype = "text/css" if fpath.suffix == ".css" else \
                    "application/javascript" if fpath.suffix == ".js" else \
                    "text/plain"
            return self._serve_file(fpath, ctype)
        
        return self.send_error(404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        content_length = int(self.headers.get("Content-Length", 0))
        body = {}
        if content_length > 0:
            try:
                body = json.loads(self.rfile.read(content_length).decode("utf-8"))
            except Exception:
                return self._send_res({"success": False, "error": "Invalid JSON"}, 400)

        # API Routes (POST)
        if path == "/api/commit":
            return self._send_res(self.service.commit(body.get("message", "Update"), body.get("author", "Deep Studio")))
            
        if path == "/api/save":
            return self._send_res(self.service.save_file(body.get("path", ""), body.get("content", "")))
            
        if path == "/api/branch/checkout":
            return self._send_res(self.service.checkout_branch(body.get("branch") or body.get("name", "")))
            
        if path == "/api/branch/create":
            return self._send_res(self.service.create_branch(body.get("name", ""), body.get("start_point", "HEAD")))
            
        if path == "/api/merge":
            return self._send_res(self.service.merge_branch(body.get("branch") or body.get("name", "")))
            
        if path == "/api/pr/create":
            return self._send_res(self.service.create_pr(body))
            
        if path == "/api/pr/review":
            return self._send_res(self.service.review_pr(body))

        if path == "/api/pr/merge":
            return self._send_res(self.service.merge_local_pr(body))
            
        if path == "/api/issue/create":
            return self._send_res(self.service.create_issue(body))

        return self.send_error(404)

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
    print(f"Deep Studio (Pinnacle) running at http://{host}:{port}")
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=".")
    parser.add_argument("--port", type=int, default=9000)
    args = parser.parse_args()
    start_dashboard(Path(args.repo).absolute(), port=args.port)
